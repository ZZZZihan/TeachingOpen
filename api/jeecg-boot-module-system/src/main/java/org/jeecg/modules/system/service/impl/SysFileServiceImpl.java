package org.jeecg.modules.system.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.jeecg.modules.common.util.QiniuUtil;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.system.mapper.SysFileMapper;
import org.jeecg.modules.system.service.ISysFileService;
import org.jeecg.modules.system.service.LocalFileReferenceResolver;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import lombok.extern.slf4j.Slf4j;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

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
@Slf4j
public class SysFileServiceImpl extends ServiceImpl<SysFileMapper, SysFile> implements ISysFileService {
    @Autowired
    QiniuUtil qiniuUtil;
    @Value(value = "${jeecg.path.upload}")
    private String uploadpath;
    @Autowired private PlatformTransactionManager transactionManager;
    @Autowired private LocalFileReferenceResolver references;

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
        if (file == null || file.getFilePath() == null || file.getFilePath().trim().isEmpty()
                || baseMapper.referenceCount(file) > 0) return true;
        boolean courseMedia = baseMapper.hasCourseMediaTable() > 0;
        if (courseMedia && baseMapper.courseMediaReferenceCount(file) > 0) return true;
        if (!Integer.valueOf(1).equals(file.getFileLocation())) return false;
        // Raw SQL matches remain conservative, including legacy cloud keys and
        // IDs. Local URL/HTML/JSON references use exactly the write/read parser;
        // otherwise an encoded live reference could be erased as "unused".
        return containsReference(baseMapper.encodedReferenceCandidates(), file.getFilePath())
                || (courseMedia && containsReference(baseMapper.encodedCourseMediaCandidates(), file.getFilePath()));
    }

    private boolean containsReference(java.util.List<java.util.Map<String, Object>> candidates, String key) {
        for (java.util.Map<String, Object> row : candidates) {
            for (Object value : row.values()) {
                if (value != null && references.resolve(value.toString()).keys().contains(key)) return true;
            }
        }
        return false;
    }

    @Override
    public boolean deleteWithFile(String id) {
        try {
            // The same row lock is held by attachment writers. READ_COMMITTED
            // makes the reference scan see a writer which committed while this
            // deletion was waiting, even when invoked from another transaction.
            Boolean prepared = cleanupTransaction().execute(status -> {
                SysFile file = lockFile(id);
                if (file == null) return true;
                if (!id.equals(file.getId()) || isReferenced(file) || !validStorage(file)) return false;
                if (!Integer.valueOf(1).equals(file.getDelFlag())
                        && !updateById(new SysFile().setId(id).setDelFlag(1))) {
                    throw new JeecgBootException("文件删除登记失败");
                }
                return true;
            });
            if (!Boolean.TRUE.equals(prepared)) return false;
            // Commit the tombstone before any irreversible storage operation.
            // On I/O, SQL or commit failure it remains available to the owner for
            // retry, while new references and downloads reject it. A failed
            // cleanup returns false rather than claiming the bytes were erased.
            return Boolean.TRUE.equals(cleanupTransaction().execute(status -> {
                SysFile file = lockFile(id);
                if (file == null) return true;
                if (!id.equals(file.getId()) || !Integer.valueOf(1).equals(file.getDelFlag())
                        || isReferenced(file) || !deleteStoredObject(file)) return false;
                if (!removeById(id)) throw new JeecgBootException("文件清理登记失败");
                return true;
            }));
        } catch (RuntimeException error) {
            log.warn("File cleanup deferred; fileId={}", id, error);
            return false;
        }
    }

    private TransactionTemplate cleanupTransaction() {
        TransactionTemplate transaction = new TransactionTemplate(transactionManager);
        transaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        transaction.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
        return transaction;
    }

    private SysFile lockFile(String id) {
        return getOne(new QueryWrapper<SysFile>().eq("id", id).last("FOR UPDATE"));
    }

    private boolean validStorage(SysFile file) {
        return Integer.valueOf(2).equals(file.getFileLocation())
                ? file.getFilePath() != null && !file.getFilePath().trim().isEmpty()
                : Integer.valueOf(1).equals(file.getFileLocation()) && localPath(file) != null;
    }

    private boolean deleteStoredObject(SysFile file) {
        if (Integer.valueOf(2).equals(file.getFileLocation())){
            return qiniuUtil.deleteFileByKey(file.getFilePath());
        }else if (Integer.valueOf(1).equals(file.getFileLocation())){
            try {
                java.nio.file.Path path = localPath(file);
                if (path == null) return false;
                Files.deleteIfExists(path);
                return true;
            }catch (Exception e){
                return false;
            }
        }
        return false;
    }

    private java.nio.file.Path localPath(SysFile file) {
        try {
            if (file.getFilePath() == null || file.getFilePath().trim().isEmpty()) return null;
            File root = new File(uploadpath).getCanonicalFile();
            java.nio.file.Path relative = java.nio.file.Paths.get(file.getFilePath());
            if (relative.isAbsolute() || file.getFilePath().contains("\\") || file.getFilePath().contains(":")) return null;
            java.nio.file.Path cursor = root.toPath();
            for (java.nio.file.Path segment : relative) {
                if (segment.toString().equals("..") || segment.toString().equals(".")) return null;
                cursor = cursor.resolve(segment);
                if (Files.isSymbolicLink(cursor)) return null;
            }
            File savedFile = cursor.toFile().getCanonicalFile();
            if (!savedFile.toPath().startsWith(root.toPath()) || savedFile.equals(root)
                    || (savedFile.exists() && !savedFile.isFile())) return null;
            return savedFile.toPath();
        }catch (Exception e){
            return null;
        }
    }

    @Override
    public boolean deleteByKeyWithFile(String key) {
        java.util.List<SysFile> matches = list(new QueryWrapper<SysFile>().eq("file_path", key));
        return matches.isEmpty() || (matches.size() == 1 && deleteWithFile(matches.get(0).getId()));
    }
}
