package org.jeecg.modules.system.service;

import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import lombok.extern.slf4j.Slf4j;
import org.jeecg.common.constant.WebsocketConst;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.modules.message.websocket.WebSocket;
import org.jeecg.modules.system.entity.SysAnnouncement;
import org.jeecg.modules.system.entity.SysAnnouncementSend;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysAnnouncementMapper;
import org.jeecg.modules.system.mapper.SysAnnouncementSendMapper;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.model.AnnouncementCommand;
import org.jeecg.modules.teaching.util.RichTextSanitizer;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationAdapter;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.util.*;
import java.util.stream.Collectors;

/** All HTTP-authored notifications and audience changes share this transaction boundary. */
@Service
@Slf4j
public class AnnouncementCommandService {
    private final AnnouncementAccessService access;
    private final SysAnnouncementMapper announcements;
    private final SysAnnouncementSendMapper recipients;
    private final SysUserMapper users;
    private final WebSocket socket;

    public AnnouncementCommandService(AnnouncementAccessService access, SysAnnouncementMapper announcements,
            SysAnnouncementSendMapper recipients, SysUserMapper users, WebSocket socket) {
        this.access = access; this.announcements = announcements; this.recipients = recipients;
        this.users = users; this.socket = socket;
    }

    private SysAnnouncement lockManaged(String id) {
        access.requireManager();
        SysAnnouncement existing = announcements.selectForUpdate(id);
        if (existing == null || !"0".equals(existing.getDelFlag())) throw new JeecgBootException("未找到对应通知");
        return existing;
    }

    private SysAnnouncement editable(AnnouncementCommand command) {
        if (command == null || command.getTitile() == null || command.getTitile().trim().isEmpty()
                || command.getTitile().length() > 100 || !Arrays.asList("ALL", "USER").contains(command.getMsgType())
                || !Arrays.asList("1", "2").contains(command.getMsgCategory()))
            throw new JeecgBootException("通知标题、类型或分类不正确");
        if (command.getPriority() != null && !Arrays.asList("L", "M", "H").contains(command.getPriority()))
            throw new JeecgBootException("通知优先级不正确");
        if (command.getStartTime() != null && command.getEndTime() != null && !command.getStartTime().before(command.getEndTime()))
            throw new JeecgBootException("结束时间需大于开始时间");
        List<String> selected = "USER".equals(command.getMsgType())
                ? AccountAdministrationService.ids(command.getUserIds()) : Collections.emptyList();
        if (!selected.isEmpty()) {
            Set<String> found = users.selectList(new LambdaQueryWrapper<SysUser>().in(SysUser::getId, selected)
                    .eq(SysUser::getDelFlag, 0).eq(SysUser::getStatus, 1)).stream().map(SysUser::getId).collect(Collectors.toSet());
            if (!found.equals(new HashSet<>(selected))) throw new JeecgBootException("未找到全部目标用户");
        }
        SysAnnouncement patch = new SysAnnouncement();
        patch.setTitile(command.getTitile().trim()); patch.setMsgContent(RichTextSanitizer.sanitize(command.getMsgContent()));
        patch.setStartTime(command.getStartTime()); patch.setEndTime(command.getEndTime());
        patch.setPriority(command.getPriority() == null ? "L" : command.getPriority());
        patch.setMsgCategory(command.getMsgCategory()); patch.setMsgType(command.getMsgType());
        patch.setUserIds(selected.isEmpty() ? "" : String.join(",", selected) + ","); patch.setMsgAbstract(command.getMsgAbstract());
        return patch;
    }

    private void synchronizeRecipients(SysAnnouncement announcement) {
        // Existing readers of an ALL notice keep their read state. Eligibility is checked on every read.
        if ("ALL".equals(announcement.getMsgType())) return;
        List<String> selected = "USER".equals(announcement.getMsgType())
                ? AccountAdministrationService.ids(announcement.getUserIds()) : Collections.emptyList();
        LambdaQueryWrapper<SysAnnouncementSend> obsolete = new LambdaQueryWrapper<SysAnnouncementSend>()
                .eq(SysAnnouncementSend::getAnntId, announcement.getId());
        if (!selected.isEmpty()) obsolete.notIn(SysAnnouncementSend::getUserId, selected);
        recipients.delete(obsolete);
        for (String userId : selected) ensureRecipient(announcement.getId(), userId);
    }

    private void ensureRecipient(String announcementId, String userId) {
        if (recipients.selectCount(new LambdaQueryWrapper<SysAnnouncementSend>()
                .eq(SysAnnouncementSend::getAnntId, announcementId).eq(SysAnnouncementSend::getUserId, userId)) == 0) {
            SysAnnouncementSend receipt = new SysAnnouncementSend();
            receipt.setAnntId(announcementId); receipt.setUserId(userId); receipt.setReadFlag("0");
            if (recipients.insert(receipt) != 1) throw new JeecgBootException("通知收件人保存失败");
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public SysAnnouncement create(AnnouncementCommand command) {
        SysUser operator = access.requireManager();
        SysAnnouncement announcement = editable(command);
        announcement.setSender(operator.getUsername()); announcement.setSendStatus("0"); announcement.setDelFlag("0");
        announcement.setCreateBy(operator.getUsername()); announcement.setCreateTime(new Date());
        if (announcements.insert(announcement) != 1) throw new JeecgBootException("通知保存失败");
        synchronizeRecipients(announcement);
        return announcement;
    }

    @Transactional(rollbackFor = Exception.class)
    public void importAnnouncements(List<AnnouncementCommand> commands) {
        access.requireManager();
        if (commands == null || commands.isEmpty() || commands.size() > 100) throw new JeecgBootException("每次可导入1至100条通知");
        for (AnnouncementCommand command : commands) create(command);
    }

    @Transactional(rollbackFor = Exception.class)
    public void edit(AnnouncementCommand command) {
        access.requireManager();
        if (command == null) throw new JeecgBootException("通知不能为空");
        SysAnnouncement existing = lockManaged(command.getId());
        SysAnnouncement patch = editable(command);
        patch.setId(existing.getId());
        patch.setUpdateBy(access.currentUser().getUsername()); patch.setUpdateTime(new Date());
        if (announcements.updateById(patch) != 1) throw new JeecgBootException("通知保存失败");
        // USER audience changes revoke removed recipients atomically with the content change.
        synchronizeRecipients(patch);
        if (AnnouncementAccessService.published(existing)) broadcastAfterCommit(patch);
    }

    @Transactional(rollbackFor = Exception.class)
    public void delete(String ids) {
        access.requireManager();
        List<SysAnnouncement> targets = AccountAdministrationService.ids(ids).stream().map(this::lockManaged).collect(Collectors.toList());
        for (SysAnnouncement target : targets) {
            SysAnnouncement patch = new SysAnnouncement(); patch.setId(target.getId()); patch.setDelFlag("1");
            if (announcements.updateById(patch) != 1) throw new JeecgBootException("通知删除失败");
        }
        for (SysAnnouncement target : targets) broadcastAfterCommit(target);
    }

    @Transactional(rollbackFor = Exception.class)
    public void publish(String id, boolean publish) {
        SysUser operator = access.requireManager();
        SysAnnouncement target = lockManaged(id);
        SysAnnouncement patch = new SysAnnouncement(); patch.setId(target.getId());
        patch.setSendStatus(publish ? "1" : "2");
        if (publish) { patch.setSender(operator.getUsername()); patch.setSendTime(new Date()); }
        else patch.setCancelTime(new Date());
        patch.setMsgContent(RichTextSanitizer.sanitize(target.getMsgContent()));
        if (announcements.updateById(patch) != 1) throw new JeecgBootException("通知发布状态更新失败");
        broadcastAfterCommit(target);
    }

    private void broadcastAfterCommit(SysAnnouncement announcement) {
        // A socket failure cannot turn an already committed write into an apparent API failure.
        Runnable broadcast = () -> {
            try {
                JSONObject event = new JSONObject();
                event.put(WebsocketConst.MSG_CMD, "ALL".equals(announcement.getMsgType()) ? WebsocketConst.CMD_TOPIC : WebsocketConst.CMD_USER);
                event.put(WebsocketConst.MSG_ID, announcement.getId());
                event.put(WebsocketConst.MSG_TXT, "通知更新");
                if ("ALL".equals(announcement.getMsgType())) socket.sendAllMessage(event.toJSONString());
                else {
                    List<SysAnnouncementSend> selected = recipients.selectList(new LambdaQueryWrapper<SysAnnouncementSend>()
                            .eq(SysAnnouncementSend::getAnntId, announcement.getId()));
                    socket.sendMoreMessage(selected.stream().map(SysAnnouncementSend::getUserId).toArray(String[]::new), event.toJSONString());
                }
            } catch (RuntimeException error) { log.warn("通知已保存，实时提醒失败；收件箱读取仍可用", error); }
        };
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronizationAdapter() {
                @Override public void afterCommit() { broadcast.run(); }
            });
        } else broadcast.run();
    }

    @Transactional(rollbackFor = Exception.class)
    public void subscribeAvailable() {
        SysUser user = access.currentUser();
        LambdaQueryWrapper<SysAnnouncement> query = new LambdaQueryWrapper<SysAnnouncement>()
                .eq(SysAnnouncement::getMsgType, "ALL").eq(SysAnnouncement::getSendStatus, "1").eq(SysAnnouncement::getDelFlag, "0")
                .and(q -> q.isNull(SysAnnouncement::getEndTime).or()
                        .ge(SysAnnouncement::getEndTime, AnnouncementAccessService.recipientCutoff(user)));
        for (SysAnnouncement announcement : announcements.selectList(query)) {
            SysAnnouncement locked = announcements.selectForUpdate(announcement.getId());
            // Recheck after locking: publication, audience or expiry may have changed since selection.
            if (!AnnouncementAccessService.published(locked) || !AnnouncementAccessService.eligibleAll(locked, user)) continue;
            ensureRecipient(locked.getId(), user.getId());
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public void markRead(String id) {
        SysUser user = access.currentUser();
        SysAnnouncement announcement = announcements.selectForUpdate(id);
        access.requireRecipient(announcement, user);
        ensureRecipient(id, user.getId());
        recipients.update(new SysAnnouncementSend(), new LambdaUpdateWrapper<SysAnnouncementSend>()
                .eq(SysAnnouncementSend::getAnntId, id).eq(SysAnnouncementSend::getUserId, user.getId())
                .set(SysAnnouncementSend::getReadFlag, "1").set(SysAnnouncementSend::getReadTime, new Date()));
    }

    @Transactional(rollbackFor = Exception.class)
    public void markAllRead() {
        recipients.markAllRead(access.currentUser().getId());
    }

    public void syncCurrentUser(String id) {
        SysUser user = access.currentUser();
        if (id != null && !id.trim().isEmpty()) access.requireRead(announcements.selectById(id));
        JSONObject event = new JSONObject(); event.put(WebsocketConst.MSG_CMD, WebsocketConst.CMD_USER);
        event.put(WebsocketConst.MSG_TXT, "通知更新");
        socket.sendOneMessage(user.getId(), event.toJSONString());
    }
}
