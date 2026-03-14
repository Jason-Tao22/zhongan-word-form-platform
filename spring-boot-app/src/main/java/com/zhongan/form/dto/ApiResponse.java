package com.zhongan.form.dto;

public record ApiResponse<T>(int code, String msg, T data) {

    public static <T> ApiResponse<T> success(T data) {
        return new ApiResponse<>(0, "success", data);
    }

    public static <T> ApiResponse<T> success(String msg, T data) {
        return new ApiResponse<>(0, msg, data);
    }

    public static <T> ApiResponse<T> failure(int code, String msg) {
        return new ApiResponse<>(code, msg, null);
    }
}
