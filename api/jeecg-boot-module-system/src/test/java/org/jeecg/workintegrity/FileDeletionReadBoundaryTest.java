package org.jeecg.workintegrity;

import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.system.service.FileAccessService;
import org.jeecg.modules.system.service.ISysFileService;
import org.jeecg.modules.system.service.LocalDownloadAccessService;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.junit.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Collections;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class FileDeletionReadBoundaryTest {
    @Test public void tombstoneStopsOwnerAdministratorAndAnonymousByteAccess() {
        LocalDownloadAccessService downloads = new LocalDownloadAccessService();
        ISysFileService files = mock(ISysFileService.class);
        TeachingAccessService access = mock(TeachingAccessService.class);
        ReflectionTestUtils.setField(downloads, "files", files);
        ReflectionTestUtils.setField(downloads, "access", access);
        SysFile tombstone = new SysFile().setId("file-a").setFilePath("private.txt")
                .setCreateBy("owner").setFileLocation(1).setDelFlag(1);
        when(files.list(any())).thenReturn(Collections.singletonList(tombstone));
        assertEquals(401, downloads.status("private.txt"));
        LoginUser owner = new LoginUser(); owner.setUsername("owner");
        when(access.currentUser()).thenReturn(owner);
        assertEquals(403, downloads.status("private.txt"));
        when(access.isAdministrator()).thenReturn(true);
        assertEquals(403, downloads.status("private.txt"));
    }

    @Test public void ownerMayRetryDeletionButCannotReadPendingMetadata() {
        FileAccessService access = spy(new FileAccessService());
        ISysFileService files = mock(ISysFileService.class);
        ReflectionTestUtils.setField(access, "files", files);
        LoginUser owner = new LoginUser(); owner.setUsername("owner");
        doReturn(owner).when(access).user(); doReturn(false).when(access).administrator();
        SysFile tombstone = new SysFile().setId("file-a").setCreateBy("owner").setDelFlag(1);
        access.requireDeletion(tombstone);
        try { access.requireRead(tombstone); fail("pending metadata must not be returned"); }
        catch (UnauthorizedException expected) { }
        tombstone.setCreateBy("another-owner");
        try { access.requireDeletion(tombstone); fail("retry must still require ownership"); }
        catch (UnauthorizedException expected) { }
    }
}
