"""文档入库管线：加载 → 清洗 → 分块 → 嵌入 → 写入 Milvus

适用于 experience（面经长文）与 knowledge（知识短文）两种 q_type；
题库 QA 对走 qa_ingest.py（整块不切）。

与 SmartQuery 的差异：分块策略路由按 q_type 而非企业文档类型；
入库携带 domain/company/difficulty 等题库元数据。
"""
import os
import re

from langchain_community.document_loaders import PyMuPDFLoader, Docx2txtLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from interviewace.backend.database.milvus import insert_documents
from interviewace.backend.logger import get_logger
from interviewace.rag.embedding import embed_documents, embed_documents_sparse

logger = get_logger(__name__)


# ==================== 文档清洗 ====================

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # 保留空白(含换行) + 可打印 ASCII + 中日韩文字 + 中文标点/全角
    allowed_chars = r'\s\x21-\x7e一-鿿　-〿＀-￯'
    text = re.sub(f'[^{allowed_chars}]', '', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = '\n'.join(line.strip() for line in text.split('\n'))
    text = re.sub(r'^第\s*\d+\s*页', '', text, flags=re.MULTILINE)
    text = re.sub(r'^共\s*\d+\s*页', '', text, flags=re.MULTILINE)
    text = re.sub(r'^Page\s+\d+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\s*/\s*\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r' +', ' ', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text.strip()


def clean_documents(docs: list[Document]) -> list[Document]:
    cleaned = []
    for doc in docs:
        cleaned_content = clean_text(doc.page_content)
        if len(cleaned_content) >= 50:
            cleaned.append(Document(page_content=cleaned_content, metadata=doc.metadata))
        else:
            logger.debug("clean_documents: skip short chunk (%d chars)", len(cleaned_content))
    logger.info("clean_documents: %d -> %d chunks", len(docs), len(cleaned))
    return cleaned


# ==================== 文件加载器 ====================

def load_file(file_path: str, q_type: str = "knowledge") -> list[Document]:
    ext = file_path.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        docs = PyMuPDFLoader(file_path).load()
        text_len = sum(len(d.page_content.strip()) for d in docs)
        # 文本层过少 → 判定为扫描件，回退 OCR（简历扫描件同样适用）
        if text_len < 50:
            logger.info("PDF 文本层过少（%d 字），回退 OCR：%s", text_len, file_path)
            docs = _load_scanned_pdf(file_path).load()
    elif ext == "docx":
        docs = Docx2txtLoader(file_path).load()
    elif ext in ("txt", "md"):
        docs = TextLoader(file_path, encoding="utf-8").load()
    elif ext == "xlsx":
        docs = _load_xlsx(file_path).load()
    elif ext in ("png", "jpg", "jpeg", "bmp", "tiff"):
        docs = _load_image(file_path).load()
    else:
        raise ValueError(f"不支持的文件类型: {ext}")
    for doc in docs:
        doc.metadata["q_type"] = q_type
        doc.metadata["file_format"] = ext
    return docs


def is_scanned(file_path: str) -> bool:
    """判断是否需要 OCR：图片文件，或文本层过短的 PDF（扫描件）"""
    ext = file_path.rsplit(".", 1)[-1].lower()
    if ext in ("png", "jpg", "jpeg", "bmp", "tiff"):
        return True
    if ext == "pdf":
        try:
            docs = PyMuPDFLoader(file_path).load()
            total = sum(len(d.page_content.strip()) for d in docs)
            return total < 50
        except Exception:
            return False
    return False


def _load_xlsx(file_path: str):
    """用 openpyxl 读取，转成 Markdown 表格文本（表格整体保留，便于结构化检索）"""
    from openpyxl import load_workbook
    wb = load_workbook(file_path, read_only=True, data_only=True)
    lines: list[str] = []
    for ws in wb.worksheets:
        lines.append(f"# {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in row]
            if any(c.strip() for c in cells):
                lines.append("| " + " | ".join(cells) + " |")
    return _StaticLoader("\n".join(lines))


class _StaticLoader:
    """把纯文本包装成 LangChain loader 接口（xlsx / OCR 转换用）"""

    def __init__(self, text: str):
        self._text = text

    def load(self) -> list[Document]:
        return [Document(page_content=self._text)]


# ==================== OCR（扫描件 / 图片） ==================== #

_ocr_client = None


def _get_ocr_client():
    global _ocr_client
    if _ocr_client is None:
        from openai import OpenAI
        from interviewace.backend.config import QWEN_API_KEY, QWEN_BASE_URL
        _ocr_client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    return _ocr_client


def _ocr_model() -> str:
    """OCR/读图用的多模态模型。

    账号的 qwen-vl 系列未开通（404），用多模态裁判模型 JUDGE_MODEL(qwen3.8-max) 替代。
    若后续开通了专用 VL 模型，在 .env 里设 QWEN_VL_OCR_MODEL 即可优先用。
    """
    from interviewace.backend.config import JUDGE_MODEL, QWEN_VL_OCR_MODEL, QWEN_MODEL
    # qwen-vl 系列未开通时回退到多模态裁判模型
    if (QWEN_VL_OCR_MODEL or "").startswith("qwen-vl"):
        return JUDGE_MODEL or QWEN_MODEL
    return QWEN_VL_OCR_MODEL or JUDGE_MODEL or QWEN_MODEL


OCR_PROMPT = "请识别图片中的全部文字，按原始阅读顺序输出纯文本；不要翻译、不要解释、不要总结。"


def _ocr_image_b64(b64_png: str) -> str:
    """调用视觉模型识别单张图片（base64 PNG）中的文字"""
    resp = _get_ocr_client().chat.completions.create(
        model=_ocr_model(),
        messages=[{"role": "user", "content": [
            {"type": "text", "text": OCR_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_png}"}},
        ]}],
    )
    return (resp.choices[0].message.content or "").strip()


def _load_scanned_pdf(file_path: str, max_pages: int = 20):
    """扫描件 PDF：逐页渲染为图片后 OCR"""
    import base64
    import fitz  # PyMuPDF

    doc = fitz.open(file_path)
    texts = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            logger.warning("扫描件页数超过上限 %d，仅处理前 %d 页", max_pages, max_pages)
            break
        pix = page.get_pixmap(dpi=150)
        b64 = base64.b64encode(pix.tobytes("png")).decode()
        try:
            text = _ocr_image_b64(b64)
            if text:
                texts.append(f"第{i + 1}页\n{text}")
        except Exception as e:
            logger.warning("OCR 第 %d 页失败：%s", i + 1, e)
    doc.close()
    return _StaticLoader("\n\n".join(texts))


def _load_image(file_path: str):
    """图片文件：直接 OCR"""
    import base64
    import io
    from PIL import Image

    img = Image.open(file_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return _StaticLoader(_ocr_image_b64(b64))


# ==================== 分块策略 ====================

parent_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
child_splitter = RecursiveCharacterTextSplitter(chunk_size=350, chunk_overlap=50)


def _split_by_headers(text: str) -> list[str]:
    """按 Markdown 标题切分，保留标题作为上下文（面经长文用）"""
    sections = re.split(r'^(#{1,4}\s+.+)$', text, flags=re.MULTILINE)
    result = []
    current_header = ""
    current_body = ""
    for part in sections:
        if re.match(r'^#{1,4}\s+', part):
            if current_body.strip():
                result.append(f"{current_header}\n{current_body.strip()}")
            current_header = part
            current_body = ""
        else:
            current_body += part
    if current_body.strip():
        result.append(f"{current_header}\n{current_body.strip()}" if current_header else current_body.strip())
    return result if result else [text]


def _split_faq(text: str) -> list[str]:
    """按 Q/A 问答对切分，问答对整体不切断"""
    pattern = r'^(Q[：:]\s*.+?)(?=Q[：:]\s*|$)'
    matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)
    if matches:
        return [m.strip() for m in matches if m.strip()]
    return [text]


def _split_by_sections(text: str) -> list[str]:
    """按二级/三级标题切分，代码块（```）整体保留不切（知识短文用）"""
    code_block = False
    sections = []
    current_header = ""
    current_body = ""

    for line in text.split('\n'):
        if line.strip().startswith('```'):
            code_block = not code_block
            current_body += line + '\n'
            continue
        if not code_block and re.match(r'^#{2,4}\s+', line):
            if current_body.strip():
                sections.append(f"{current_header}\n{current_body.strip()}" if current_header else current_body.strip())
            current_header = line
            current_body = ""
        else:
            current_body += line + '\n'

    if current_body.strip():
        sections.append(f"{current_header}\n{current_body.strip()}" if current_header else current_body.strip())

    if not sections:
        return [text]

    final = []
    for s in sections:
        if len(s) > 1200:
            final.extend(parent_splitter.split_text(s))
        else:
            final.append(s)
    return final


def _split_by_table(text: str) -> list[str]:
    """表格整体保留不切断，非表格部分按段落切"""
    lines = text.split('\n')
    result = []
    current_block = []
    in_table = False

    for line in lines:
        is_table_line = bool(re.match(r'^\s*\|', line) or re.match(r'^\s*[\-\|]{3,}', line))
        if is_table_line and not in_table:
            if current_block:
                result.append('\n'.join(current_block).strip())
                current_block = []
            in_table = True
            current_block.append(line)
        elif is_table_line and in_table:
            current_block.append(line)
        elif not is_table_line and in_table:
            result.append('\n'.join(current_block).strip())
            current_block = [line]
            in_table = False
        else:
            current_block.append(line)

    if current_block:
        result.append('\n'.join(current_block).strip())

    final = []
    for block in result:
        if len(block) > 1000 and not re.match(r'^\s*\|', block):
            final.extend(parent_splitter.split_text(block))
        else:
            final.append(block)
    return final if final else [text]


# ==================== 分块器路由（按 q_type） ====================

SPLITTER_MAP = {
    "experience": _split_by_headers,   # 面经长文：按标题切
    "knowledge": _split_by_sections,   # 知识短文：按标题切 + 代码块保护
    "faq_doc": _split_faq,             # FAQ 文档（Q:/A: 格式的汇总文档）
    "table_doc": _split_by_table,      # 含大表格的文档
}


def _doc_title(text: str) -> str:
    """取文档首个一级标题作为标题"""
    m = re.search(r'^#\s+(.+?)\s*$', text, flags=re.MULTILINE)
    return m.group(1).strip() if m else ""


def _titled(prefix: str, text: str) -> str:
    """给父块加上前缀（面经：【公司-岗位-日期】；知识短文：【标题】），避免来源混淆"""
    return f"【{prefix}】{text}" if prefix else text


def split_documents(docs: list[Document], q_type: str = "knowledge",
                    parent_prefix: str = "") -> tuple[list[str], list[str]]:
    """按 q_type 选择分块策略，生成子块和父块"""
    splitter_fn = SPLITTER_MAP.get(q_type, _split_by_headers)
    child_texts = []
    parent_texts = []

    for doc in docs:
        text = doc.page_content
        prefix = parent_prefix or _doc_title(text)
        sections = splitter_fn(text)
        for section in sections:
            parent_chunks = parent_splitter.split_text(section)
            for parent in parent_chunks:
                titled_parent = _titled(prefix, parent)
                child_chunks = child_splitter.split_text(parent)
                for child in child_chunks:
                    child_texts.append(child)
                    parent_texts.append(titled_parent)

    logger.info("split_documents q_type=%s children=%d", q_type, len(child_texts))
    return child_texts, parent_texts


# ==================== 入库 ====================

def ingest_file(file_path: str, q_type: str = "knowledge", source: str | None = None,
                title: str | None = None, url: str = "",
                domain: str = "", company: str = "", difficulty: int = 1,
                parent_prefix: str = "",
                collection_name: str | None = None) -> int:
    """文档入库管线：load → clean → split → embed(双通道) → upsert

    q_type: experience（面经）/ knowledge（知识短文）。题库 QA 对走 qa_ingest.py。
    """
    if q_type == "qa_pair":
        raise ValueError("题库 QA 对请走 qa_ingest.py（整块不切），不要用 ingest_file")

    docs = load_file(file_path, q_type=q_type)
    docs = clean_documents(docs)
    child_texts, parent_texts = split_documents(docs, q_type=q_type,
                                                parent_prefix=parent_prefix)

    if not child_texts:
        logger.warning("ingest file=%s 未产出任何块，跳过（内容可能过短）", file_path)
        return 0

    dense_vectors = embed_documents(child_texts)
    sparse_vectors = embed_documents_sparse(child_texts)

    insert_kwargs = {"collection_name": collection_name} if collection_name else {}
    source_name = source or os.path.basename(file_path)
    if title is None:
        title = _doc_title(docs[0].page_content) if docs else ""
    n = len(child_texts)
    insert_documents(child_texts, parent_texts, dense_vectors, sparse_vectors,
                     partition_name=q_type, q_type=q_type, source=source_name,
                     domains=domain, companies=company, difficulties=difficulty,
                     titles=[title] * n, urls=[url] * n, **insert_kwargs)

    logger.info("ingest file=%s q_type=%s domain=%s source=%s chunks=%d",
                file_path, q_type, domain, source_name, n)
    return n
