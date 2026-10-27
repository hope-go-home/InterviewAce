"""豆包流式语音识别 2.0（火山引擎 sauc bigmodel_async）后端封装

自实现的 sauc WebSocket 二进制协议客户端（参考官方 SDK 协议帧格式）。
音频要求：WAV，16kHz，16bit，单声道，raw PCM。

流程：建连 → 发送配置（gzip JSON）→ 分片发送音频（gzip）→ 收增量/最终识别结果 → 返回文本
"""
import asyncio
import gzip
import json
import struct
import uuid
from typing import AsyncGenerator

import aiohttp

from interviewace.backend.config import (
    VOLC_ASR_API_KEY, VOLC_ASR_ENDPOINT, VOLC_ASR_RESOURCE_ID,
)
from interviewace.backend.logger import get_logger

logger = get_logger(__name__)

# 协议常量
PV1 = 0b0001
MT_FULL_REQ = 0b0001
MT_AUDIO_ONLY = 0b0010
MT_SERVER_FULL_RESP = 0b1001
MT_SERVER_ERROR = 0b1111
FLAG_POS_SEQ = 0b0001
FLAG_NEG_WITH_SEQ = 0b0011
SER_JSON = 0b0001
COMP_GZIP = 0b0001

SEGMENT_MS = 200          # 每包音频时长
SAMPLE_RATE = 16000


def _header(message_type: int, flags: int) -> bytes:
    return bytes([
        (PV1 << 4) | 1,
        (message_type << 4) | flags,
        (SER_JSON << 4) | COMP_GZIP,
        0x00,
    ])


def _full_request(seq: int, payload: dict) -> bytes:
    body = gzip.compress(json.dumps(payload).encode("utf-8"))
    return (_header(MT_FULL_REQ, FLAG_POS_SEQ)
            + struct.pack(">i", seq) + struct.pack(">I", len(body)) + body)


def _audio_request(seq: int, segment: bytes, is_last: bool) -> bytes:
    if is_last:
        flags = FLAG_NEG_WITH_SEQ
        seq = -seq
    else:
        flags = FLAG_POS_SEQ
    body = gzip.compress(segment)
    return (_header(MT_AUDIO_ONLY, flags)
            + struct.pack(">i", seq) + struct.pack(">I", len(body)) + body)


def _parse_response(msg: bytes) -> dict:
    """解析服务端二进制帧 → dict"""
    header_size = (msg[0] & 0x0F) * 4
    message_type = msg[1] >> 4
    flags = msg[1] & 0x0F
    compression = msg[2] & 0x0F
    payload = msg[header_size:]

    is_last = bool(flags & 0x02)
    if flags & 0x01:
        payload = payload[4:]  # sequence
    if flags & 0x04:
        payload = payload[4:]  # event

    code = 0
    if message_type == MT_SERVER_FULL_RESP:
        payload = payload[4:]  # payload_size
    elif message_type == MT_SERVER_ERROR:
        code = struct.unpack(">i", payload[:4])[0]
        payload = payload[8:]

    result = {"code": code, "is_last": is_last, "text": "", "utterances": []}
    if not payload:
        return result
    # 服务端响应通常不压缩（compression=0），仅在标志为 GZIP 时解压
    if compression == COMP_GZIP:
        try:
            payload = gzip.decompress(payload)
        except Exception as e:
            logger.warning("gzip decompress failed: %s", e)
            return result
    try:
        data = json.loads(payload.decode("utf-8"))
        result["payload"] = data
        res = data.get("result") or {}
        result["text"] = res.get("text", "") or data.get("text", "")
        result["utterances"] = res.get("utterances") or data.get("utterances") or []
    except Exception as e:
        logger.warning("parse response payload failed: %s", e)
    return result


def _read_wav_pcm(wav: bytes) -> tuple[bytes, int]:
    """从 WAV 提取裸 PCM 与采样率（遍历块，兼容 fmt 块 16/18/40 字节）"""
    if len(wav) < 44 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise ValueError("不是合法的 WAV 文件")

    sample_rate, num_channels, bits = 0, 1, 16
    pos = 12                      # 从 WAVE 之后开始遍历块（不要写死偏移）
    while pos + 8 <= len(wav):
        chunk_id = wav[pos:pos + 4]
        chunk_size = struct.unpack("<I", wav[pos + 4:pos + 8])[0]
        body = pos + 8
        if chunk_id == b"fmt ":
            num_channels = struct.unpack("<H", wav[body + 2:body + 4])[0]
            sample_rate = struct.unpack("<I", wav[body + 4:body + 8])[0]
            bits = struct.unpack("<H", wav[body + 14:body + 16])[0]
        elif chunk_id == b"data":
            return wav[body:body + chunk_size], sample_rate
        pos = body + chunk_size + (chunk_size & 1)   # 块按偶数字节对齐
    raise ValueError("WAV 缺少 data 块")


def resample_pcm16(pcm: bytes, from_rate: int, to_rate: int = SAMPLE_RATE) -> bytes:
    """16bit 单声道 PCM 线性插值重采样（如 22050 → 16000）"""
    if from_rate == to_rate or not pcm:
        return pcm
    n_in = len(pcm) // 2
    samples = struct.unpack(f"<{n_in}h", pcm[:n_in * 2])
    n_out = int(n_in * to_rate / from_rate)
    ratio = from_rate / to_rate
    out = []
    for i in range(n_out):
        pos = i * ratio
        i0 = int(pos)
        i1 = min(i0 + 1, n_in - 1)
        frac = pos - i0
        out.append(int(samples[i0] + (samples[i1] - samples[i0]) * frac))
    return struct.pack(f"<{len(out)}h", *out)


async def transcribe_wav(wav_bytes: bytes) -> str:
    """把一段 WAV（16k mono 16bit）流式送豆包识别，返回最终文本（录完再识别，非实时）"""
    pcm, rate = _read_wav_pcm(wav_bytes)
    if rate != SAMPLE_RATE:
        logger.info("wav 采样率 %d → 重采样到 %d", rate, SAMPLE_RATE)
        pcm = resample_pcm16(pcm, rate, SAMPLE_RATE)

    # 分片：每片 SEGMENT_MS 毫秒的 PCM（16k*16bit*mono → 32000 字节/秒 → 6400 字节/200ms）
    seg_size = int(SAMPLE_RATE * 2 * 1 * SEGMENT_MS / 1000)
    segments = [pcm[i:i + seg_size] for i in range(0, len(pcm), seg_size)] or [b""]

    final_texts: list[str] = []
    async with DoubaoStreamSession() as sess:
        for i, seg in enumerate(segments):
            is_last = (i == len(segments) - 1)
            await sess.send_audio(seg, is_last)
            if not is_last:
                await asyncio.sleep(SEGMENT_MS / 1000)
        async for r in sess.recv_results():
            if r.get("is_final_text") and r.get("text"):
                final_texts.append(r["text"])

    text = "".join(final_texts).strip() or "（未识别到内容）"
    logger.info("stt transcribe done, %d 段，%d 字", len(final_texts), len(text))
    return text


# ---------------- 实时流式会话（边说边出字） ----------------

class DoubaoStreamSession:
    """豆包流式 ASR 会话：可持续 send_audio，同时异步收增量结果。

    用法：
        async with DoubaoStreamSession() as s:
            await s.send_audio(pcm_chunk, is_last=False)
            async for r in s.recv_results():   # r = {text, is_final_text, definite}
                ...
    """

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._ws = None
        self._seq = 1
        self._closed = False

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        headers = {
            "X-Api-Key": VOLC_ASR_API_KEY,
            "X-Api-Resource-Id": VOLC_ASR_RESOURCE_ID,
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        self._ws = await self._session.ws_connect(VOLC_ASR_ENDPOINT, headers=headers)
        payload = _build_payload()
        await self._ws.send_bytes(_full_request(self._seq, payload))
        self._seq += 1
        # 读配置回包（忽略内容，仅确认握手）
        msg = await self._ws.receive()
        if msg.type not in (aiohttp.WSMsgType.BINARY,):
            raise RuntimeError("豆包 ASR 握手失败")
        logger.info("doubao stream session ready")
        return self

    async def __aexit__(self, *exc):
        self._closed = True
        try:
            if self._ws and not self._ws.closed:
                await self._ws.close()
        finally:
            if self._session and not self._session.closed:
                await self._session.close()

    async def send_audio(self, pcm: bytes, is_last: bool = False) -> None:
        if self._closed or not self._ws:
            return
        await self._ws.send_bytes(_audio_request(self._seq, pcm, is_last))
        if not is_last:
            self._seq += 1

    async def finish(self) -> None:
        """发送结束包（最后一包 seq 取负）"""
        if self._closed or not self._ws:
            return
        await self._ws.send_bytes(_audio_request(self._seq, b"", True))
        self._closed = True

    async def recv_results(self) -> AsyncGenerator[dict, None]:
        """异步收识别结果：{(text, is_final_text)}"""
        if self._ws is None:
            return
        while True:
            try:
                msg = await self._ws.receive()
            except Exception as e:
                logger.warning("ws receive failed: %s", e)
                break
            if msg.type == aiohttp.WSMsgType.BINARY:
                r = _parse_response(msg.data)
                if r.get("code"):
                    logger.warning("doubao asr error code=%s", r["code"])
                    break
                utts = r.get("utterances") or []
                definite_text = "".join(u.get("text", "") for u in utts if u.get("definite"))
                partial_text = "".join(u.get("text", "") for u in utts)
                text = definite_text or partial_text or r.get("text", "")
                if text:
                    yield {"text": text, "is_final_text": bool(definite_text) or r.get("is_last")}
                if r.get("is_last"):
                    break
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED,
                              aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING):
                break


def _build_payload() -> dict:
    return {
        "user": {"uid": "interviewace"},
        "audio": {"format": "pcm", "codec": "raw", "rate": SAMPLE_RATE, "bits": 16, "channel": 1},
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": True,
            "show_utterances": True,
            "end_window_size": 800,   # 静音 800ms 判停
        },
    }
