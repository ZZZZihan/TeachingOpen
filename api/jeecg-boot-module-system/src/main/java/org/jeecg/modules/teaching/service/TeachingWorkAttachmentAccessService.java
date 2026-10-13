package org.jeecg.modules.teaching.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.system.service.ISysFileService;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.Set;
import java.util.TreeSet;

/** Authorize references before saving the work which could otherwise authorize reads. */
@Service
public class TeachingWorkAttachmentAccessService {
    @Autowired private TeachingAccessService access;
    @Autowired private ISysFileService files;

    /** The caller must first authorize and lock an existing work in its write transaction. */
    public void requireWrite(TeachingWork requested, TeachingWork existing) {
        LoginUser user = access.currentUser();
        if (user == null) throw new UnauthorizedException("请先登录");
        Set<String> references = new TreeSet<>();
        if (requested.getWorkFile() != null && !requested.getWorkFile().isEmpty()) references.add(requested.getWorkFile());
        if (requested.getWorkCover() != null && !requested.getWorkCover().isEmpty()) references.add(requested.getWorkCover());
        // Stable lock order also covers a file reused as the cover.
        for (String id : references) {
            SysFile file = files.getOne(new QueryWrapper<SysFile>().eq("id", id).last("FOR UPDATE"));
            boolean retained = existing != null && (id.equals(existing.getWorkFile()) || id.equals(existing.getWorkCover()));
            if (file == null || !id.equals(file.getId()) || !Integer.valueOf(0).equals(file.getDelFlag())
                    || (!retained && !access.isAdministrator() && !user.getUsername().equals(file.getCreateBy()))) {
                throw new UnauthorizedException("无附件使用权限");
            }
        }
    }
}
