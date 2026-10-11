package org.jeecg.workintegrity;

import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.system.service.ISysFileService;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.jeecg.modules.teaching.entity.TeachingWorkCorrect;
import org.jeecg.modules.teaching.mapper.TeachingWorkMapper;
import org.jeecg.modules.teaching.mapper.TeachingWorkCorrectMapper;
import org.jeecg.modules.teaching.mapper.TeachingWorkCommentMapper;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.jeecg.modules.teaching.service.TeachingWorkAttachmentAccessService;
import org.jeecg.modules.teaching.service.impl.TeachingWorkServiceImpl;
import org.junit.Before;
import org.junit.Test;
import org.mockito.InOrder;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Collections;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class WorkAttachmentAuthorizationTest {
    private TeachingWorkServiceImpl service;
    private TeachingWorkAttachmentAccessService attachments;
    private TeachingAccessService access;
    private ISysFileService files;
    private TeachingWorkMapper works;
    private TeachingWorkCorrectMapper feedback;
    private TeachingWorkCommentMapper comments;
    private TeachingWork stored;
    private SysFile file;

    @Before public void setup() {
        service = new TeachingWorkServiceImpl();
        attachments = new TeachingWorkAttachmentAccessService();
        access = mock(TeachingAccessService.class); files = mock(ISysFileService.class);
        works = mock(TeachingWorkMapper.class); feedback = mock(TeachingWorkCorrectMapper.class);
        comments = mock(TeachingWorkCommentMapper.class);
        ReflectionTestUtils.setField(attachments, "access", access);
        ReflectionTestUtils.setField(attachments, "files", files);
        ReflectionTestUtils.setField(service, "attachmentAccess", attachments);
        ReflectionTestUtils.setField(service, "teachingAccessService", access);
        ReflectionTestUtils.setField(service, "teachingWorkMapper", works);
        ReflectionTestUtils.setField(service, "teachingWorkCorrectMapper", feedback);
        ReflectionTestUtils.setField(service, "teachingWorkCommentMapper", comments);
        LoginUser teacher = new LoginUser(); teacher.setId("teacher-id"); teacher.setUsername("teacher");
        when(access.currentUser()).thenReturn(teacher);
        stored = new TeachingWork(); stored.setId("managed-work"); stored.setUserId("student");
        stored.setDepartId("class-a"); stored.setWorkFile("shared-original"); stored.setWorkCover("shared-cover");
        stored.setWorkStatus("1"); stored.setDelFlag(0);
        file = new SysFile().setId("private").setCreateBy("other-uploader").setDelFlag(0);
        when(files.getOne(any())).thenReturn(file);
        when(works.selectOne(any())).thenReturn(stored);
    }

    private TeachingWork update(String fileId, String coverId) {
        TeachingWork request = new TeachingWork(); request.setId("managed-work");
        request.setWorkFile(fileId); request.setWorkCover(coverId); request.setWorkStatus("3");
        return request;
    }

    private void deny(Runnable action) {
        try { action.run(); fail("Private file reference must be rejected before writing"); }
        catch (UnauthorizedException expected) { assertEquals("无附件使用权限", expected.getMessage()); }
        verify(works, never()).insert(any()); verify(works, never()).updateById(any());
        verifyZeroInteractions(feedback, comments);
    }

    @Test public void teacherCannotAttachPrivateFileAndPublishOrReplaceFeedback() {
        deny(() -> service.updateMain(update("private", null), Collections.singletonList(new TeachingWorkCorrect()), Collections.emptyList()));
        assertEquals("shared-original", stored.getWorkFile()); assertEquals("1", stored.getWorkStatus());
        InOrder order = inOrder(works, access, files);
        order.verify(works).selectOne(argThat(q -> q.getSqlSegment().contains("FOR UPDATE")));
        order.verify(access).requireManageWork(stored);
        order.verify(access).currentUser();
        order.verify(files).getOne(argThat(q -> q.getSqlSegment().contains("FOR UPDATE")));
    }

    @Test public void privateCoverIsDeniedBeforeFeedbackDeletion() {
        deny(() -> service.updateMain(update(null, "private"), Collections.emptyList(), Collections.emptyList()));
    }

    @Test public void teacherCannotUsePrivateFileOnNewWork() {
        deny(() -> service.saveMain(update("private", null), Collections.emptyList(), Collections.emptyList()));
    }

    @Test public void teacherCanUseOwnUploadedReplacement() {
        file.setCreateBy("teacher");
        TeachingWork request = update("private", null);
        service.updateMain(request, null, null);
        verify(works).updateById(request); verifyZeroInteractions(feedback, comments);
        assertEquals("student", request.getUserId()); assertEquals("class-a", request.getDepartId());
    }

    @Test public void sentCopyRetainsForeignAttachmentAndCanBeGradedWithoutSendingAttachments() {
        file.setId("shared-original");
        service.updateMain(update("shared-original", null), Collections.singletonList(new TeachingWorkCorrect()), null);
        verify(works).updateById(any()); verify(feedback).deleteByMainId("managed-work"); verify(feedback).insert(any());
        clearInvocations(works, feedback, files);
        service.updateMain(update(null, null), null, null);
        verify(works).updateById(any()); verifyZeroInteractions(files, feedback);
    }

    @Test public void missingDeletedAndCollationAliasFilesCannotBeAttachedEvenByAdmin() {
        when(access.isAdministrator()).thenReturn(true);
        when(files.getOne(any())).thenReturn(null);
        deny(() -> service.saveMain(update("private", null), null, null));
        when(files.getOne(any())).thenReturn(file.setDelFlag(1));
        deny(() -> service.saveMain(update("private", null), null, null));
        file.setDelFlag(0);
        deny(() -> service.saveMain(update("PRIVATE", null), null, null));
    }

    @Test public void adminCanAttachAnExistingLiveFileOnImport() {
        when(access.isAdministrator()).thenReturn(true);
        TeachingWork request = update("private", null);
        service.saveMain(request, null, null);
        verify(works).insert(request);
    }

    @Test public void retainedAttachmentNeverAppliesToANewOrDifferentWork() {
        file.setId("shared-original");
        deny(() -> service.saveMain(update("shared-original", null), null, null));
    }

    @Test public void sourceFileAndCoverHaveOneStableOrderedLock() {
        file.setCreateBy("teacher");
        attachments.requireWrite(update("private", "private"), null);
        verify(files, times(1)).getOne(any());
    }
}
