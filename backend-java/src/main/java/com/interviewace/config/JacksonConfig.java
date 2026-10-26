package com.interviewace.config;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.fasterxml.jackson.datatype.jsr310.deser.LocalDateTimeDeserializer;
import com.fasterxml.jackson.datatype.jsr310.ser.LocalDateTimeSerializer;

/**
 * Jackson 序列化约定：
 * LocalDateTime → "yyyy-MM-dd HH:mm:ss"（与 Python str(datetime) 输出对齐，
 * 前端 created_at.slice(0,10) 取日期的行为完全兼容）。
 */
@Configuration
public class JacksonConfig {

    public static final DateTimeFormatter DATETIME_PATTERN = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    @Bean
    public Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> builder
                .serializers(new LocalDateTimeSerializer(DATETIME_PATTERN))
                .deserializers(new LocalDateTimeDeserializer(DATETIME_PATTERN));
    }
}
