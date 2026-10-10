package org.jeecg.modules.system.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.jeecg.modules.common.util.QiniuUtil;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.system.mapper.SysFileMapper;
import org.jeecg.modules.system.service.ISysFileService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;

import java.io.File;
import java.nio.file.Files;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.CommonUtils;
import org.jeecg.common.exception.JeecgBootException;
import org.springframework.transaction.annotation.Transactional;

/**
 * @Description: 文件管理
 * @Author: jeecg-boot
 * @Date:   2020-04-11
 * @Version: V1.0
 */
@Service
public class SysFileServiceImpl extends ServiceImpl<SysFileMapper, SysFile> implements ISysFileService {
    @Autowired
    QiniuUtil qiniuUtil;
    @Value(value = "${jeecg.path.upload}")
    private String uploadpath;

    @Override
    @Transactional
    public SysFile recordUpload(String path, String originalName, int location) {
        LoginUser user = (LoginUser) SecurityUtils.getSubject().getPrincipal();
        if (user == null) throw new UnauthorizedException("请先登录");
        SysFile file = new SysFile();
        String name = CommonUtils.getFileName(originalName == null ? "未命名文件" : originalName);
        file.setId(java.util.UUID.randomUUID().toString().replace("-", ""));
        file.setFilePath(path).setFileLocation(location).setFileName(name.length() > 128 ? name.substring(0, 128) : name);
        file.setCreateBy(user.getUsername()).setCreateTime(new java.util.Date()).setSysOrgCode(user.getOrgCode()).setDelFlag(0);
        if (!save(file)) throw new JeecgBootException("文件登记失败");
        return file;
    }

    @Override
    public boolean isReferenced(SysFile file) {
        return file == null || file.getFilePath() == null || file.getFilePath().trim().isEmpty()
                || baseMapper.referenceCount(file) > 0
                || (baseMapper.hasCourseMediaTable() > 0 && baseMapper.courseMediaReferenceCount(file) > 0);
    }

    @Override
    public boolean deleteWithFile(String id) {
        SysFile file = this.getById(id);
        if (file == null){
            return true;
        }
        if (isReferenced(file)) return false;
        if (Integer.valueOf(2).equals(file.getFileLocation())){
            if (qiniuUtil.deleteFileByKey(file.getFilePath())){
                return this.removeById(id);
            }else{
                return false;
            }
        }else if (Integer.valueOf(1).equals(file.getFileLocation())){
            try {
                if (file.getFilePath() == null || file.getFilePath().trim().isEmpty()) return false;
                File root = new File(uploadpath).getCanonicalFile();
                java.nio.file.Path relative = java.nio.file.Paths.get(file.getFilePath());
                if (relative.isAbsolute() || file.getFilePath().contains("\\") || file.getFilePath().contains(":")) return false;
                java.nio.file.Path cursor = root.toPath();
                for (java.nio.file.Path segment : relative) {
                    if (segment.toString().equals("..") || segment.toString().equals(".")) return false;
                    cursor = cursor.resolve(segment);
                    if (Files.isSymbolicLink(cursor)) return false;
                }
                File savedFile = cursor.toFile().getCanonicalFile();
                if (!savedFile.toPath().startsWith(root.toPath()) || savedFile.equals(root)
                        || (savedFile.exists() && !savedFile.isFile())) return false;
                // A missing object is already reclaimed; an I/O failure must keep
                // its metadata for a later retry instead of silently losing it.
                Files.deleteIfExists(savedFile.toPath());
                return this.removeById(id);
            }catch (Exception e){
                return false;
            }
        }
        return false;
    }

    @Override
    public boolean deleteByKeyWithFile(String key) {
        java.util.List<SysFile> matches = list(new QueryWrapper<SysFile>().eq("file_path", key));
        return matches.isEmpty() || (matches.size() == 1 && deleteWithFile(matches.get(0).getId()));
    }
}
