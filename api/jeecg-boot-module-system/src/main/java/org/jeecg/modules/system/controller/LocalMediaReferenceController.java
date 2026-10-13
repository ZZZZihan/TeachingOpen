package org.jeecg.modules.system.controller;

import org.jeecg.common.api.vo.Result;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.modules.system.service.LocalMediaReferenceIndex;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Explicit repair after an authorized external data import; never run from a download. */
@RestController
@RequestMapping("/sys/localMediaReferences")
public class LocalMediaReferenceController {
    @Autowired private TeachingAccessService access;
    @Autowired private LocalMediaReferenceIndex index;

    @PostMapping("/rebuild")
    public Result<?> rebuild() {
        if (access.currentUser() == null || !access.isAdministrator()) throw new UnauthorizedException("无媒体索引管理权限");
        return Result.ok(index.rebuild(true));
    }
}
