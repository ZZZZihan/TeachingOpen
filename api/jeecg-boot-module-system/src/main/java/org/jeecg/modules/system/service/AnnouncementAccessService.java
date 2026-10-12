package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.SysAnnmentTypeEnum;
import org.jeecg.modules.system.entity.SysAnnouncement;
import org.jeecg.modules.system.entity.SysAnnouncementSend;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysAnnouncementSendMapper;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.mapper.SysUserRoleMapper;
import org.jeecg.modules.system.model.AnnouncementSendModel;
import org.jeecg.modules.teaching.util.RichTextSanitizer;
import org.springframework.stereotype.Service;

import java.util.Date;
import java.util.List;

/** Management grants and recipient access intentionally remain separate. */
@Service
public class AnnouncementAccessService {
    private final SysUserMapper users;
    private final SysUserRoleMapper roles;
    private final SysAnnouncementSendMapper recipients;

    public AnnouncementAccessService(SysUserMapper users, SysUserRoleMapper roles, SysAnnouncementSendMapper recipients) {
        this.users = users; this.roles = roles; this.recipients = recipients;
    }

    public SysUser currentUser() {
        Object principal = SecurityUtils.getSubject().getPrincipal();
        if (!(principal instanceof LoginUser)) throw new UnauthorizedException("请先登录");
        SysUser user = users.selectById(((LoginUser) principal).getId());
        if (user == null || !Integer.valueOf(0).equals(user.getDelFlag()) || !Integer.valueOf(1).equals(user.getStatus()))
            throw new UnauthorizedException("账户不可用");
        return user;
    }

    public boolean isManager(SysUser user) {
        List<String> assigned = roles.getRoleByUserId(user.getId());
        return assigned != null && (assigned.contains("admin") || assigned.contains("dev"));
    }

    public SysUser requireManager() {
        SysUser user = currentUser();
        if (!isManager(user)) throw new UnauthorizedException("没有通知管理权限");
        return user;
    }

    public void requireRecipient(SysAnnouncement announcement, SysUser user) {
        if (!published(announcement)) throw new UnauthorizedException("没有此通知的读取权限");
        if (!eligibleAll(announcement, user) && !("USER".equals(announcement.getMsgType()) && recipients.selectCount(
                new LambdaQueryWrapper<SysAnnouncementSend>().eq(SysAnnouncementSend::getAnntId, announcement.getId())
                        .eq(SysAnnouncementSend::getUserId, user.getId())) > 0))
            throw new UnauthorizedException("没有此通知的读取权限");
    }

    /** Missing historical account dates still permit active notices, without granting expired history. */
    public static Date recipientCutoff(SysUser user) {
        return user.getCreateTime() == null ? new Date() : user.getCreateTime();
    }

    public static boolean eligibleAll(SysAnnouncement announcement, SysUser user) {
        return announcement != null && "ALL".equals(announcement.getMsgType())
                && (announcement.getEndTime() == null || !announcement.getEndTime().before(recipientCutoff(user)));
    }

    public SysAnnouncement requireRead(SysAnnouncement announcement) {
        SysUser user = currentUser();
        if (!isManager(user)) requireRecipient(announcement, user);
        else if (announcement == null || !"0".equals(announcement.getDelFlag()))
            throw new UnauthorizedException("没有此通知的读取权限");
        return safe(announcement);
    }

    public static boolean published(SysAnnouncement announcement) {
        return announcement != null && "0".equals(announcement.getDelFlag()) && "1".equals(announcement.getSendStatus());
    }

    public static SysAnnouncement safe(SysAnnouncement announcement) {
        if (announcement != null) {
            announcement.setMsgContent(RichTextSanitizer.sanitize(announcement.getMsgContent()));
            if (!safeNavigation(announcement.getBusType(), announcement.getOpenType(), announcement.getOpenPage())) {
                announcement.setOpenType(null); announcement.setOpenPage(null);
            }
        }
        return announcement;
    }

    public static AnnouncementSendModel safe(AnnouncementSendModel message) {
        message.setMsgContent(RichTextSanitizer.sanitize(message.getMsgContent()));
        if (!safeNavigation(message.getBusType(), message.getOpenType(), message.getOpenPage())) {
            message.setOpenType(null); message.setOpenPage(null);
        }
        return message;
    }

    private static boolean safeNavigation(String businessType, String openType, String openPage) {
        SysAnnmentTypeEnum configured = SysAnnmentTypeEnum.getByType(businessType);
        return configured != null && configured.getOpenType().equals(openType) && configured.getOpenPage().equals(openPage);
    }
}
