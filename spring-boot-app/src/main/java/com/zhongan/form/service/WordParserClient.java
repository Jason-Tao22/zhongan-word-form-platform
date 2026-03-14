package com.zhongan.form.service;

import java.util.Map;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class WordParserClient {
    private final WebClient webClient;

    public WordParserClient(WebClient wordParserWebClient) {
        this.webClient = wordParserWebClient;
    }

    public Map<String, Object> parseWord(MultipartFile file) {
        try {
            return parseWord(file.getOriginalFilename(), file.getBytes());
        } catch (Exception e) {
            throw new IllegalStateException("Python 微服务调用失败: " + e.getMessage(), e);
        }
    }

    public Map<String, Object> parseWord(String filename, byte[] fileBytes) {
        try {
            ByteArrayResource resource = new ByteArrayResource(fileBytes) {
                @Override
                public String getFilename() {
                    return filename;
                }
            };

            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("file", resource);

            return webClient.post()
                .uri(uriBuilder -> uriBuilder.path("/parse-word")
                    .queryParam("include_prototype", true)
                    .build())
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(body))
                .exchangeToMono(response -> {
                    if (response.statusCode().is2xxSuccessful()) {
                        return response.bodyToMono(Map.class);
                    }
                    return response.bodyToMono(Map.class)
                        .defaultIfEmpty(Map.of())
                        .flatMap(payload -> Mono.error(new IllegalStateException(extractErrorMessage(payload))));
                })
                .block();
        } catch (IllegalStateException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalStateException("Python 微服务调用失败: " + e.getMessage(), e);
        }
    }

    public Map<String, Object> getParserStatus() {
        try {
            return webClient.get()
                .uri("/config-status")
                .exchangeToMono(response -> {
                    if (response.statusCode().is2xxSuccessful()) {
                        return response.bodyToMono(Map.class);
                    }
                    return response.bodyToMono(Map.class)
                        .defaultIfEmpty(Map.of())
                        .flatMap(payload -> Mono.error(new IllegalStateException(extractErrorMessage(payload))));
                })
                .block();
        } catch (IllegalStateException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalStateException("Python 微服务状态获取失败: " + e.getMessage(), e);
        }
    }

    private String extractErrorMessage(Map<?, ?> payload) {
        Object detail = payload.get("detail");
        if (detail != null) {
            return String.valueOf(detail);
        }
        Object msg = payload.get("msg");
        if (msg != null) {
            return String.valueOf(msg);
        }
        return "Python 微服务返回错误";
    }
}
