package com.zhongan.form.controller;

import com.zhongan.form.dto.ApiResponse;
import com.zhongan.form.service.SubmissionService;
import jakarta.validation.constraints.Min;
import java.util.Map;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/forms")
public class FormController {
    private final SubmissionService submissionService;

    public FormController(SubmissionService submissionService) {
        this.submissionService = submissionService;
    }

    @PostMapping("/{templateId}/submissions")
    public ApiResponse<Map<String, Object>> createSubmission(
        @PathVariable String templateId,
        @RequestBody Map<String, Object> body,
        @RequestHeader(name = "X-User", defaultValue = "operator") String submittedBy
    ) {
        return ApiResponse.success(submissionService.createSubmission(templateId, body, submittedBy));
    }

    @GetMapping("/{templateId}/submissions")
    public ApiResponse<Map<String, Object>> listSubmissions(
        @PathVariable String templateId,
        @RequestParam(defaultValue = "1") @Min(1) int page,
        @RequestParam(defaultValue = "20") @Min(1) int size,
        @RequestParam(required = false) String status
    ) {
        return ApiResponse.success(submissionService.listSubmissions(templateId, page, size, status));
    }

    @GetMapping("/submissions/{submissionId}")
    public ApiResponse<Map<String, Object>> getSubmission(@PathVariable Long submissionId) {
        return ApiResponse.success(submissionService.getSubmission(submissionId));
    }

    @PutMapping("/submissions/{submissionId}")
    public ApiResponse<Map<String, Object>> updateDraft(
        @PathVariable Long submissionId,
        @RequestBody Map<String, Object> body,
        @RequestHeader(name = "X-User", defaultValue = "operator") String submittedBy
    ) {
        return ApiResponse.success(submissionService.updateDraft(submissionId, body, submittedBy));
    }

    @DeleteMapping("/submissions/{submissionId}")
    public ApiResponse<Void> deleteDraft(@PathVariable Long submissionId) {
        submissionService.deleteDraft(submissionId);
        return ApiResponse.success("删除成功", null);
    }

    @PostMapping("/submissions/{submissionId}/submit")
    public ApiResponse<Void> submit(@PathVariable Long submissionId) {
        submissionService.updateStatus(submissionId, "submitted");
        return ApiResponse.success("已提交审核", null);
    }

    @PostMapping("/submissions/{submissionId}/approve")
    public ApiResponse<Void> approve(@PathVariable Long submissionId) {
        submissionService.updateStatus(submissionId, "approved");
        return ApiResponse.success("审批通过", null);
    }

    @PostMapping("/submissions/{submissionId}/reject")
    public ApiResponse<Void> reject(@PathVariable Long submissionId) {
        submissionService.updateStatus(submissionId, "rejected");
        return ApiResponse.success("已驳回", null);
    }
}
