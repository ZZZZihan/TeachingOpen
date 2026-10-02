package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.apache.commons.lang.StringUtils;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.AuthorizationException;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.common.util.QiniuUtil;
import org.jeecg.modules.common.util.QiniuUploadPolicy;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.jeecg.modules.teaching.mapper.TeachingWorkMapper;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import java.util.List;
import org.springframework.transaction.annotation.Transactional;

/** Resource authorization at public file-management entry points. */
@Service
public class FileAccessService {
    @Autowired private ISysFileService files;
    @Autowired private TeachingWorkMapper works;
    @Autowired private TeachingAccessService teachingAccess;
    @Autowired private QiniuUtil qiniu;
    @Value("${jeecg.uploadType}") private String uploadType;

    public LoginUser user() {
        LoginUser user = (LoginUser) SecurityUtils.getSubject().getPrincipal();
        if (user == null) throw new UnauthorizedException("请先登录");
        return user;
    }

    public boolean administrator() { return teachingAccess.isAdministrator(); }

    public void requireOwner(SysFile file) {
        if (file == null || (!administrator() && !user().getUsername().equals(file.getCreateBy()))) {
            throw new UnauthorizedException("无文件管理权限");
        }
    }

    public void requireRead(SysFile file) {
        if (file == null || !Integer.valueOf(0).equals(file.getDelFlag())) throw new UnauthorizedException("文件不存在或无访问权限");
        if (administrator() || user().getUsername().equals(file.getCreateBy())) return;
        for (TeachingWork work : works.selectList(new QueryWrapper<TeachingWork>().eq("work_file", file.getId()).or().eq("work_cover", file.getId()))) {
            try { teachingAccess.requireCommunityWork(work); return; }
            catch (AuthorizationException denied) { /* Try another shared reference. */ }
        }
        throw new UnauthorizedException("无文件访问权限");
    }

    @Transactional
    public SysFile register(SysFile request) {
        validateDisplay(request);
        if (StringUtils.isBlank(request.getFilePath()) || request.getFileLocation() == null) throw new JeecgBootException("文件路径和存储位置不能为空");
        List<SysFile> matches = files.list(new QueryWrapper<SysFile>().eq("file_path", request.getFilePath()).eq("file_location", request.getFileLocation()));
        SysFile file;
        if (matches.size() > 1) throw new JeecgBootException("文件路径存在重复记录，请联系管理员");
        if (matches.size() == 1) {
            file = matches.get(0);
            requireOwner(file);
            if (!Integer.valueOf(0).equals(file.getDelFlag())) throw new JeecgBootException("文件不可用");
        } else if (Integer.valueOf(2).equals(request.getFileLocation()) && "qiniu".equals(uploadType)) {
            QiniuUploadPolicy.requireOwnedKey(user().getId(), request.getFilePath());
            if (!qiniu.fileExists(request.getFilePath())) throw new JeecgBootException("请先完成文件上传");
            file = files.recordUpload(request.getFilePath(), request.getFileName(), 2);
        } else {
            throw new UnauthorizedException("只能登记本人已上传的文件");
        }
        updateDisplay(file, request);
        return files.getById(file.getId());
    }

    public void updateDisplay(SysFile file, SysFile request) {
        requireOwner(file);
        validateDisplay(request);
        SysFile update = new SysFile().setId(file.getId()).setFileName(request.getFileName())
                .setFileTag(request.getFileTag()).setFileType(request.getFileType())
                .setUpdateBy(user().getUsername()).setUpdateTime(new java.util.Date());
        if (!files.updateById(update)) throw new JeecgBootException("文件更新失败");
    }

    private void validateDisplay(SysFile request) {
        if (request.getFileName() != null && (request.getFileName().trim().isEmpty() || request.getFileName().length() > 128)) throw new JeecgBootException("文件名应为 1 至 128 个字符");
        if (request.getFileTag() != null && request.getFileTag().length() > 32) throw new JeecgBootException("文件标签不能超过 32 个字符");
        if (request.getFileType() != null && (request.getFileType() < 1 || request.getFileType() > 5)) throw new JeecgBootException("文件类型不合法");
    }

    public void requireDeletion(SysFile file) {
        requireOwner(file);
        if (files.isReferenced(file)) throw new JeecgBootException("文件仍被使用，请先移除引用");
    }
}
