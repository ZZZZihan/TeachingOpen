package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.Set;

/** Check local references before the new teaching object can confer access to them. */
@Service
public class LocalFileReferenceAccessService {
    @Autowired private LocalFileReferenceResolver references;
    @Autowired private LocalDownloadAccessService downloads;
    @Autowired private ISysFileService files;
    @Autowired private TeachingAccessService access;
    @Value("${jeecg.path.upload}") private String uploadPath;

    public void requireUse(String... values) {
        if (access.currentUser() == null) throw new UnauthorizedException("请先登录");
        if (access.isAdministrator()) return;
        Set<String> keys = new HashSet<>();
        Set<String> localUrls = new HashSet<>();
        for (String value : values) {
            LocalFileReferenceResolver.References found = references.resolve(value);
            keys.addAll(found.keys());
            localUrls.addAll(found.localUrls());
        }
        for (String key : keys) {
            // Plain description text and external URLs are not local resources.
            // Also recognize legacy files without a sys_file row, because the
            // existing download resolver supports their course/assignment refs.
            boolean resource = localUrls.contains(key) || storedLocally(key)
                    || files.count(new QueryWrapper<SysFile>().eq("file_location", 1).eq("file_path", key)) > 0;
            if (resource && downloads.status(key) != 200) throw new UnauthorizedException("无附件使用权限");
        }
    }

    private boolean storedLocally(String key) {
        try {
            Path root = Paths.get(uploadPath).toAbsolutePath().normalize();
            Path path = root.resolve(key).normalize();
            return path.startsWith(root) && !path.equals(root) && Files.isRegularFile(path);
        } catch (InvalidPathException invalid) { return false; }
    }
}
