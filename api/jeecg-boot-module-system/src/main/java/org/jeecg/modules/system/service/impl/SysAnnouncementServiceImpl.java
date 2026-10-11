package org.jeecg.modules.system.service.impl;

import java.util.Date;
import java.util.List;
import javax.annotation.Resource;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.constant.CommonConstant;
import org.jeecg.modules.system.entity.SysAnnouncement;
import org.jeecg.modules.system.mapper.SysAnnouncementMapper;
import org.jeecg.modules.system.model.AnnouncementCommand;
import org.jeecg.modules.system.service.AnnouncementAccessService;
import org.jeecg.modules.system.service.AnnouncementCommandService;
import org.jeecg.modules.system.service.ISysAnnouncementService;
import org.jeecg.modules.teaching.util.RichTextSanitizer;
import org.springframework.stereotype.Service;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;

@Service
public class SysAnnouncementServiceImpl extends ServiceImpl<SysAnnouncementMapper, SysAnnouncement> implements ISysAnnouncementService {
    @Resource private SysAnnouncementMapper sysAnnouncementMapper;
    @Resource private AnnouncementCommandService announcementCommands;
    @Resource private AnnouncementAccessService announcementAccess;

    @Override
    public void saveAnnouncement(SysAnnouncement announcement) {
        SysAnnouncement saved = announcementCommands.create(AnnouncementCommand.from(announcement));
        announcement.setId(saved.getId());
    }

    @Override
    public boolean upDateAnnouncement(SysAnnouncement announcement) {
        announcementCommands.edit(AnnouncementCommand.from(announcement));
        return true;
    }

    /** Trusted internal workflow producer; never exposed as an HTTP management bypass. */
    @Override
    public void saveSysAnnouncement(String title, String msgContent) {
        SysAnnouncement announcement = new SysAnnouncement();
        announcement.setTitile(title);
        announcement.setMsgContent(RichTextSanitizer.sanitize(msgContent));
        announcement.setSender("JEECG BOOT");
        announcement.setPriority(CommonConstant.PRIORITY_L);
        announcement.setMsgType(CommonConstant.MSG_TYPE_ALL);
        announcement.setSendStatus(CommonConstant.HAS_SEND);
        announcement.setSendTime(new Date());
        announcement.setDelFlag(CommonConstant.DEL_FLAG_0.toString());
        sysAnnouncementMapper.insert(announcement);
    }

    @Override
    public Page<SysAnnouncement> querySysCementPageByUserId(Page<SysAnnouncement> page, String userId, String msgCategory) {
        if (!announcementAccess.currentUser().getId().equals(userId)) throw new UnauthorizedException("只能读取本人的通知");
        List<SysAnnouncement> rows = sysAnnouncementMapper.querySysCementListByUserId(page, userId, msgCategory);
        rows.forEach(AnnouncementAccessService::safe);
        return page.setRecords(rows);
    }
}
