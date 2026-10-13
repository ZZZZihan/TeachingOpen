package org.jeecg.notification;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.exception.JeecgBootExceptionHandler;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.message.controller.SysMessageController;
import org.jeecg.modules.message.controller.SysMessageTemplateController;
import org.jeecg.modules.message.websocket.WebSocket;
import org.jeecg.modules.system.controller.*;
import org.jeecg.modules.system.entity.*;
import org.jeecg.modules.system.mapper.*;
import org.jeecg.modules.system.model.AnnouncementCommand;
import org.jeecg.modules.system.service.*;
import org.junit.*;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.io.ByteArrayOutputStream;
import java.util.*;
import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

public class AnnouncementAuthorizationTest {
    private SysUserMapper users;
    private SysUserRoleMapper roles;
    private SysAnnouncementMapper announcements;
    private SysAnnouncementSendMapper recipients;
    private AnnouncementAccessService access;
    private AnnouncementCommandService commands;
    private WebSocket socket;
    private SysUser actor;
    private MockMvc http;
    private ISysAnnouncementService reads;
    private SysAnnouncement existing;

    @Before public void setup() {
        for (Class<?> entity : Arrays.asList(SysUser.class, SysAnnouncement.class, SysAnnouncementSend.class))
            TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new MybatisConfiguration(), "notification-test"), entity);
        users = mock(SysUserMapper.class); roles = mock(SysUserRoleMapper.class);
        announcements = mock(SysAnnouncementMapper.class); recipients = mock(SysAnnouncementSendMapper.class); socket = mock(WebSocket.class);
        access = new AnnouncementAccessService(users, roles, recipients);
        commands = new AnnouncementCommandService(access, announcements, recipients, users, socket);
        actor = new SysUser().setId("actor").setUsername("fixture_admin").setStatus(1).setDelFlag(0).setCreateTime(new Date(1000));
        LoginUser principal = new LoginUser(); principal.setId("actor"); principal.setUsername("stale-name");
        Subject subject = mock(Subject.class); when(subject.getPrincipal()).thenReturn(principal); ThreadContext.bind(subject);
        when(users.selectById("actor")).thenReturn(actor);
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("admin"));
        when(users.selectList(any())).thenReturn(Collections.singletonList(new SysUser().setId("recipient")));
        when(announcements.insert(any(SysAnnouncement.class))).thenAnswer(call -> { ((SysAnnouncement)call.getArgument(0)).setId("generated"); return 1; });
        when(announcements.updateById(any(SysAnnouncement.class))).thenReturn(1);
        when(recipients.insert(any(SysAnnouncementSend.class))).thenReturn(1);
        when(recipients.selectList(any())).thenReturn(Collections.emptyList());
        existing = new SysAnnouncement(); existing.setId("existing"); existing.setMsgType("ALL"); existing.setSendStatus("1"); existing.setDelFlag("0");
        existing.setMsgContent("<p>Safe</p><img src='data:image/png;base64,broken' onerror='document.body.dataset.executed=1'>");
        when(announcements.selectForUpdate("existing")).thenReturn(existing);
        when(announcements.selectById("existing")).thenReturn(existing);
        reads = mock(ISysAnnouncementService.class); when(reads.getById("existing")).thenReturn(existing);
        SysAnnouncementController controller = new SysAnnouncementController();
        ReflectionTestUtils.setField(controller, "announcementAccess", access); ReflectionTestUtils.setField(controller, "announcementCommands", commands);
        ReflectionTestUtils.setField(controller, "sysAnnouncementService", reads);
        SysAnnouncementSendController receiver = new SysAnnouncementSendController();
        ReflectionTestUtils.setField(receiver, "announcementAccess", access); ReflectionTestUtils.setField(receiver, "announcementCommands", commands);
        ReflectionTestUtils.setField(receiver, "sysAnnouncementService", reads);
        ReflectionTestUtils.setField(receiver, "sysAnnouncementSendService", mock(ISysAnnouncementSendService.class));
        SysMessageController messages = new SysMessageController(); ReflectionTestUtils.setField(messages, "announcementAccess", access);
        SysMessageTemplateController templates = new SysMessageTemplateController(); ReflectionTestUtils.setField(templates, "announcementAccess", access);
        http = MockMvcBuilders.standaloneSetup(controller, receiver, messages, templates).setControllerAdvice(new JeecgBootExceptionHandler()).build();
    }
    @After public void cleanup() {
        ThreadContext.unbindSubject();
        if (TransactionSynchronizationManager.isSynchronizationActive()) TransactionSynchronizationManager.clearSynchronization();
    }
    private AnnouncementCommand draft(String type) {
        AnnouncementCommand command = new AnnouncementCommand(); command.setTitile("Fixture notice"); command.setMsgCategory("1");
        command.setMsgType(type); command.setUserIds("recipient,"); command.setMsgContent(existing.getMsgContent()); return command;
    }
    private void deny(Runnable operation) {
        try { operation.run(); fail("Expected authorization refusal"); } catch (UnauthorizedException expected) { }
    }

    @Test public void studentAndTeacherManagementDeniedBeforeAnyWriteOrBroadcast() {
        for (String role : Arrays.asList("student", "teacher")) {
            when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList(role));
            deny(() -> commands.create(draft("ALL"))); deny(() -> commands.edit(draft("ALL")));
            deny(() -> commands.delete("existing")); deny(() -> commands.publish("existing", true));
            deny(() -> commands.publish("existing", false)); deny(() -> commands.importAnnouncements(Collections.singletonList(draft("ALL"))));
        }
        verifyZeroInteractions(announcements, recipients, socket);
    }

    @Test public void controllerManagementAndLegacyRecipientRoutesRejectOrdinaryLogin() throws Exception {
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("student"));
        for (String path : Arrays.asList("/sys/annountCement/list", "/sys/annountCement/exportXls", "/sys/annountCement/doReleaseData?id=existing", "/sys/annountCement/doReovkeData?id=existing", "/sys/sysAnnouncementSend/list", "/message/sysMessage/list", "/message/sysMessage/exportXls", "/message/sysMessage/queryById?id=x", "/message/sysMessageTemplate/list", "/message/sysMessageTemplate/exportXls", "/message/sysMessageTemplate/queryById?id=x"))
            http.perform(get(path)).andExpect(status().isOk()).andExpect(jsonPath("$.code").value(510)).andExpect(jsonPath("$.success").value(false));
        for (String prefix : Arrays.asList("/sys/annountCement", "/sys/sysAnnouncementSend", "/message/sysMessage", "/message/sysMessageTemplate")) {
            http.perform(post(prefix + "/add").contentType("application/json").content("{}")).andExpect(jsonPath("$.code").value(510));
            http.perform(put(prefix + "/edit").contentType("application/json").content("{}")).andExpect(jsonPath("$.code").value(510));
            http.perform(delete(prefix + "/delete?id=existing")).andExpect(jsonPath("$.code").value(510));
            http.perform(delete(prefix + "/deleteBatch?ids=existing")).andExpect(jsonPath("$.code").value(510));
        }
        for (String prefix : Arrays.asList("/sys/annountCement", "/message/sysMessage", "/message/sysMessageTemplate"))
            http.perform(post(prefix + "/importExcel")).andExpect(jsonPath("$.code").value(510));
        http.perform(post("/message/sysMessageTemplate/sendMsg").contentType("application/json").content("{}")).andExpect(jsonPath("$.code").value(510));
        verifyZeroInteractions(announcements, recipients, socket);
    }

    @Test public void liveRoleRevocationAndDisabledAccountIgnoreCachedPrincipal() {
        assertEquals("fixture_admin", access.requireManager().getUsername());
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("teacher"));
        deny(() -> commands.publish("existing", true));
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("admin")); actor.setStatus(2);
        deny(() -> commands.create(draft("ALL")));
        verifyZeroInteractions(announcements, recipients, socket);
    }

    @Test public void dtoDoesNotAcceptIdentityPublicationAuditOrRoutingFields() throws Exception {
        AnnouncementCommand command = new ObjectMapper().readValue("{\"id\":\"forged-id\",\"titile\":\"notice\",\"msgType\":\"ALL\",\"msgCategory\":\"1\",\"sender\":\"forged\",\"sendStatus\":\"1\",\"createBy\":\"forged\",\"delFlag\":\"1\",\"openPage\":\"bad\",\"openType\":\"component\"}", AnnouncementCommand.class);
        SysAnnouncement created = commands.create(command);
        assertEquals("generated", created.getId()); assertEquals("fixture_admin", created.getSender());
        assertEquals("fixture_admin", created.getCreateBy()); assertEquals("0", created.getSendStatus()); assertEquals("0", created.getDelFlag());
        assertNull(created.getOpenPage()); assertNull(created.getOpenType()); assertNull(created.getSendTime()); assertNull(created.getCancelTime());
        verifyZeroInteractions(socket);
    }

    @Test public void administratorCanCreateTargetedNoticeWithSanitizedContent() {
        SysAnnouncement created = commands.create(draft("USER"));
        assertEquals("recipient,", created.getUserIds()); assertTrue(created.getMsgContent().contains("<p>Safe</p>"));
        assertFalse(created.getMsgContent().contains("onerror"));
        ArgumentCaptor<SysAnnouncementSend> receipt = ArgumentCaptor.forClass(SysAnnouncementSend.class);
        verify(recipients).insert(receipt.capture()); assertEquals("recipient", receipt.getValue().getUserId());
        assertEquals("0", receipt.getValue().getReadFlag()); assertNull(receipt.getValue().getReadTime());
    }

    @Test public void editPreservesProtectedFieldsAndDoesNotPublishDraft() {
        existing.setSendStatus("0"); AnnouncementCommand command = draft("USER"); command.setId("existing");
        commands.edit(command);
        ArgumentCaptor<SysAnnouncement> patch = ArgumentCaptor.forClass(SysAnnouncement.class); verify(announcements).updateById(patch.capture());
        assertEquals("existing", patch.getValue().getId()); assertNull(patch.getValue().getSender()); assertNull(patch.getValue().getSendStatus());
        assertNull(patch.getValue().getCreateBy()); assertNull(patch.getValue().getDelFlag()); assertNull(patch.getValue().getSendTime());
        verify(recipients).delete(any()); verify(recipients).insert(any(SysAnnouncementSend.class)); verifyZeroInteractions(socket);
    }

    @Test public void broadcastOccursOnlyAfterCommitAndFailureCannotUndoSuccess() {
        TransactionSynchronizationManager.initSynchronization(); commands.publish("existing", true);
        verifyZeroInteractions(socket); assertEquals(1, TransactionSynchronizationManager.getSynchronizations().size());
        doThrow(new IllegalStateException("fixture socket failure")).when(socket).sendAllMessage(anyString());
        for (TransactionSynchronization synchronization : TransactionSynchronizationManager.getSynchronizations()) synchronization.afterCommit();
        verify(socket).sendAllMessage(anyString()); verify(announcements).updateById(any(SysAnnouncement.class));
    }

    @Test public void persistenceFailureDoesNotRegisterOrSendBroadcast() {
        when(announcements.updateById(any(SysAnnouncement.class))).thenThrow(new IllegalStateException("fixture database failure"));
        TransactionSynchronizationManager.initSynchronization();
        try { commands.publish("existing", true); fail("failure swallowed"); } catch (IllegalStateException expected) { }
        assertTrue(TransactionSynchronizationManager.getSynchronizations().isEmpty()); verifyZeroInteractions(socket);
    }

    @Test public void recipientCanReadOwnNoticeButNotDraftRevokedOrForeignAudience() throws Exception {
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("student"));
        http.perform(get("/sys/annountCement/queryById?id=existing")).andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.result.msgContent").value(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("onerror"))));
        existing.setSendStatus("0"); deny(() -> access.requireRead(existing));
        existing.setSendStatus("2"); deny(() -> access.requireRead(existing));
        existing.setSendStatus("1"); existing.setMsgType("USER"); deny(() -> access.requireRead(existing));
        when(recipients.selectCount(any())).thenReturn(1); assertSame(existing, access.requireRead(existing));
    }

    @Test public void legacyAccountWithoutRegistrationTimeReceivesActiveAllButNotExpiredHistory() {
        actor.setCreateTime(null);
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("student"));
        existing.setEndTime(new Date(System.currentTimeMillis() + 60000));
        assertSame(existing, access.requireRead(existing));
        existing.setEndTime(new Date(System.currentTimeMillis() - 60000));
        deny(() -> access.requireRead(existing));
        existing.setEndTime(null);
        assertSame(existing, access.requireRead(existing));
        verifyZeroInteractions(recipients);
    }

    @Test public void allNoticeKeepsRegistrationBoundaryForKnownAccounts() {
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("teacher"));
        existing.setEndTime(new Date(999));
        deny(() -> access.requireRead(existing));
        existing.setEndTime(new Date(1000));
        assertSame(existing, access.requireRead(existing));
        existing.setEndTime(new Date(2000));
        assertSame(existing, access.requireRead(existing));
    }

    @Test public void legacyAccountSubscriptionBindsNonNullCutoffAndKeepsOwnReceipt() {
        actor.setCreateTime(null);
        existing.setEndTime(new Date(System.currentTimeMillis() + 60000));
        when(announcements.selectList(any())).thenReturn(Collections.singletonList(existing));
        long before = System.currentTimeMillis();
        commands.subscribeAvailable();
        ArgumentCaptor<LambdaQueryWrapper> query = ArgumentCaptor.forClass(LambdaQueryWrapper.class);
        verify(announcements).selectList(query.capture()); query.getValue().getSqlSegment();
        Collection<Object> parameters = query.getValue().getParamNameValuePairs().values();
        assertFalse(parameters.contains(null));
        assertTrue(parameters.stream().anyMatch(value -> value instanceof Date && ((Date)value).getTime() >= before));
        ArgumentCaptor<SysAnnouncementSend> receipt = ArgumentCaptor.forClass(SysAnnouncementSend.class);
        verify(recipients).insert(receipt.capture());
        assertEquals("actor", receipt.getValue().getUserId()); assertEquals("existing", receipt.getValue().getAnntId());
        verifyZeroInteractions(socket);
    }

    @Test public void actualXlsxImportUsesSanitizedDraftCommandAndIgnoresForgedPublication() throws Exception {
        XSSFWorkbook workbook = new XSSFWorkbook();
        org.apache.poi.ss.usermodel.Sheet sheet = workbook.createSheet("通知");
        sheet.createRow(0).createCell(0).setCellValue("合成通知导入"); sheet.createRow(1);
        String[][] rows = {{"标题", "内容", "优先级", "消息类型", "通告对象类型", "发布状态", "发布人"},
                {"XLSX fixture", existing.getMsgContent(), "L", "1", "ALL", "1", "forged_sender"}};
        for (int i = 0; i < rows.length; i++) {
            org.apache.poi.ss.usermodel.Row row = sheet.createRow(i + 2);
            for (int j = 0; j < rows[i].length; j++) row.createCell(j).setCellValue(rows[i][j]);
        }
        ByteArrayOutputStream output = new ByteArrayOutputStream(); workbook.write(output);
        http.perform(multipart("/sys/annountCement/importExcel").file(new MockMultipartFile("file", "fixture.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", output.toByteArray())))
                .andExpect(status().isOk()).andExpect(jsonPath("$.success").value(true));
        ArgumentCaptor<SysAnnouncement> saved = ArgumentCaptor.forClass(SysAnnouncement.class);
        verify(announcements).insert(saved.capture());
        assertEquals("XLSX fixture", saved.getValue().getTitile());
        assertEquals("0", saved.getValue().getSendStatus()); assertEquals("fixture_admin", saved.getValue().getSender());
        assertTrue(saved.getValue().getMsgContent().contains("<p>Safe</p>"));
        assertFalse(saved.getValue().getMsgContent().contains("onerror")); verifyZeroInteractions(socket);
    }

    @Test public void readReceiptUsesBoundIdAndCannotCreateForeignAudience() {
        existing.setMsgType("USER"); when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("student"));
        deny(() -> commands.markRead("existing")); deny(() -> commands.markRead("existing' OR '1'='1"));
        verify(recipients, never()).update(any(), any()); verify(recipients, never()).insert(any(SysAnnouncementSend.class));
        when(recipients.selectCount(any())).thenReturn(1); commands.markRead("existing");
        ArgumentCaptor<LambdaUpdateWrapper> query = ArgumentCaptor.forClass(LambdaUpdateWrapper.class);
        verify(recipients).update(any(SysAnnouncementSend.class), query.capture());
        String sql = query.getValue().getSqlSegment(); assertFalse(sql.contains("existing")); assertFalse(sql.contains("actor"));
        assertTrue(query.getValue().getParamNameValuePairs().containsValue("existing")); assertTrue(query.getValue().getParamNameValuePairs().containsValue("actor"));
    }

    @Test public void notificationSyncTargetsOnlyCurrentUserAndForeignNoticeDenied() {
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("student"));
        commands.syncCurrentUser("existing"); commands.syncCurrentUser(null);
        verify(socket, times(2)).sendOneMessage(eq("actor"), anyString()); verify(socket, never()).sendAllMessage(anyString());
        existing.setMsgType("USER"); deny(() -> commands.syncCurrentUser("existing"));
        verifyNoMoreInteractions(socket);
    }

    @Test public void historicalNavigationIsLimitedToServerDefinedBusinessDestinations() {
        existing.setOpenType("component"); existing.setOpenPage("system/UserList");
        AnnouncementAccessService.safe(existing); assertNull(existing.getOpenType()); assertNull(existing.getOpenPage());
        existing.setBusType("bpm"); existing.setOpenType("url"); existing.setOpenPage("/bpm/task/MyTaskList");
        AnnouncementAccessService.safe(existing); assertEquals("/bpm/task/MyTaskList", existing.getOpenPage());
        existing.setOpenPage("javascript:document.body.dataset.executed=1");
        AnnouncementAccessService.safe(existing); assertNull(existing.getOpenPage());
    }
}
