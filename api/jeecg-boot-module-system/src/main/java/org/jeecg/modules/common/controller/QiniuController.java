package org.jeecg.modules.common.controller;

import com.qiniu.util.Auth;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.config.QiniuConfig;
import org.jeecg.modules.common.util.QiniuUploadPolicy;
import org.jeecg.modules.system.service.FileAccessService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/common/qiniu")
public class QiniuController {
    @Autowired private FileAccessService files;
    @Value("${jeecg.uploadType}") private String uploadType;

    /** Keep the existing token string result and add the required object-key prefix. */
    public static class UploadTokenResult extends Result<String> {
        private final String keyPrefix;
        public UploadTokenResult(String prefix) { this.keyPrefix = prefix; }
        public String getKeyPrefix() { return keyPrefix; }
    }

    @GetMapping("/getToken")
    public Result<String> getQiniuToken() { return issue(null); }

    @GetMapping("/getTokenByKey")
    public Result<String> getQiniuTokenByKey(@RequestParam String key) { return issue(key); }

    private Result<String> issue(String key) {
        if (!"qiniu".equals(uploadType)) throw new JeecgBootException("当前未启用七牛上传");
        String userId = files.user().getId();
        UploadTokenResult result = new UploadTokenResult(QiniuUploadPolicy.prefix(userId));
        result.setCode(200);
        result.setResult(QiniuUploadPolicy.token(Auth.create(QiniuConfig.key, QiniuConfig.secret),
                QiniuConfig.bucket, userId, key, QiniuConfig.expires));
        return result;
    }
}
