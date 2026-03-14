package com.zhongan.form.controller;

import com.zhongan.form.dto.ApiResponse;
import com.zhongan.form.service.TemplateService;
import jakarta.validation.constraints.Min;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/templates")
public class TemplateController {
    private final TemplateService templateService;

    public TemplateController(TemplateService templateService) {
        this.templateService = templateService;
    }

    @PostMapping("/upload")
    public ApiResponse<Map<String, Object>> upload(
        @RequestParam("file") MultipartFile file,
        @RequestHeader(name = "X-User", defaultValue = "admin") String createdBy
    ) {
        return ApiResponse.success(templateService.upload(file, createdBy));
    }

    @PostMapping("/{templateId}/publish")
    public ApiResponse<Map<String, Object>> publish(@PathVariable String templateId) {
        return ApiResponse.success(templateService.publish(templateId));
    }

    @PostMapping("/{templateId}/retry")
    public ApiResponse<Map<String, Object>> retry(@PathVariable String templateId) {
        return ApiResponse.success(templateService.retry(templateId));
    }

    @GetMapping
    public ApiResponse<Map<String, Object>> list(
        @RequestParam(defaultValue = "1") @Min(1) int page,
        @RequestParam(defaultValue = "20") @Min(1) int size,
        @RequestParam(required = false) String keyword
    ) {
        return ApiResponse.success(templateService.list(page, size, keyword));
    }

    @GetMapping("/{templateId}")
    public ApiResponse<Map<String, Object>> detail(
        @PathVariable String templateId,
        @RequestParam(name = "includeContent", defaultValue = "true") boolean includeContent
    ) {
        return ApiResponse.success(templateService.getTemplateDetail(templateId, includeContent));
    }

    @GetMapping("/{templateId}/schema")
    public Map<String, Object> schema(@PathVariable String templateId) {
        return templateService.getSchema(templateId);
    }

    @GetMapping("/{templateId}/content")
    public ApiResponse<Map<String, Object>> content(@PathVariable String templateId) {
        return ApiResponse.success(templateService.getTemplateContent(templateId));
    }

    @PutMapping("/{templateId}/schema")
    public ApiResponse<Map<String, Object>> updateSchema(
        @PathVariable String templateId,
        @RequestBody Map<String, Object> schema
    ) {
        return ApiResponse.success(templateService.updateSchema(templateId, schema));
    }

    @GetMapping("/parser-status")
    public ApiResponse<Map<String, Object>> parserStatus() {
        return ApiResponse.success(templateService.getParserStatus());
    }

    @DeleteMapping("/{templateId}")
    @ResponseStatus(HttpStatus.OK)
    public ApiResponse<Void> delete(@PathVariable String templateId) {
        templateService.delete(templateId);
        return ApiResponse.success("删除成功", null);
    }
}
