package org.jeecg.workintegrity;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.service.ISysFileService;
import org.jeecg.modules.system.service.LocalDownloadAccessService;
import org.jeecg.modules.system.service.LocalFileReferenceAccessService;
import org.jeecg.modules.system.service.LocalFileReferenceResolver;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class LocalFileReferenceAuthorizationTest {
    private static final String DOMAIN = "http://localhost:8080/api/sys/common/static";
    @Rule public TemporaryFolder temporary = new TemporaryFolder();
    private LocalFileReferenceResolver resolver;
    private LocalFileReferenceAccessService service;
    private LocalDownloadAccessService downloads;
    private ISysFileService files;
    private TeachingAccessService access;

    @Before public void setup() throws Exception {
        resolver = new LocalFileReferenceResolver();
        ReflectionTestUtils.setField(resolver, "json", new ObjectMapper());
        ReflectionTestUtils.setField(resolver, "staticDomain", DOMAIN);
        service = new LocalFileReferenceAccessService();
        downloads = mock(LocalDownloadAccessService.class); files = mock(ISysFileService.class);
        access = mock(TeachingAccessService.class);
        when(access.currentUser()).thenReturn(new LoginUser());
        ReflectionTestUtils.setField(service, "references", resolver);
        ReflectionTestUtils.setField(service, "downloads", downloads);
        ReflectionTestUtils.setField(service, "files", files);
        ReflectionTestUtils.setField(service, "access", access);
        ReflectionTestUtils.setField(service, "uploadPath", temporary.getRoot().getAbsolutePath());
        temporary.newFile("private.txt");
        when(downloads.status(anyString())).thenReturn(403);
    }

    private void denied(String... values) {
        try { service.requireUse(values); fail("New reference cannot confer private local-file access"); }
        catch (UnauthorizedException expected) { assertEquals("无附件使用权限", expected.getMessage()); }
    }

    @Test public void privateRawAndEncodedUrlsHtmlAndJsonAreRejected() {
        for (String value : new String[]{"private.txt", DOMAIN + "/private.txt", DOMAIN + "/%70rivate%2etxt",
                "<img src='" + DOMAIN + "/&#x70;rivate.txt'>", "<video poster=private.txt>",
                "{\"images\":[{\"src\":\"" + DOMAIN + "/%70rivate.txt\"}]}",
                "[\"private.txt\"]", "external.txt,private.txt"}) {
            denied(value);
        }
        verify(downloads, times(8)).status("private.txt");
    }

    @Test public void legacyUnregisteredPrivateBytesDoNotBecomeReadableThroughNewReference() {
        assertEquals(0, files.count(null));
        denied("private.txt");
        verify(downloads).status("private.txt");
    }

    @Test public void registeredFileIsProtectedWhenLocalBytesAreCurrentlyMissing() {
        when(files.count(any())).thenReturn(1);
        denied("registered-missing.txt");
        verify(downloads).status("registered-missing.txt");
    }

    @Test public void alreadyReadableReferencesAllowRetentionAndLegitimateSharing() {
        when(downloads.status("private.txt")).thenReturn(200);
        service.requireUse("private.txt", "<img src='" + DOMAIN + "/%70rivate.txt'>");
        verify(downloads, times(1)).status("private.txt");
    }

    @Test public void externalImagesAndOrdinaryDescriptionTextAreNotRejected() {
        service.requireUse("<p>练习说明</p><img src='https://cdn.example.test/images/a.png'>",
                "https://cdn.example.test/document.pdf", "讲解文字", "", null);
        verifyZeroInteractions(downloads);
    }

    @Test public void explicitLocalUrlCannotHideBehindEarlierUnregisteredPlainValue() {
        denied("not-uploaded.txt", DOMAIN + "/not-uploaded.txt");
        verify(downloads).status("not-uploaded.txt");
    }

    @Test public void onlyExactConfiguredOriginAndOnceDecodedValidUtf8IdentifyLocalKeys() {
        assertTrue(resolver.resolve(DOMAIN + "/%E4%BD%9C%E4%B8%9A%20a.txt?download=1#x").keys().contains("作业 a.txt"));
        assertTrue(resolver.resolve(DOMAIN + "/percent%2520.txt").keys().contains("percent%20.txt"));
        assertFalse(resolver.resolve(DOMAIN + "/percent%2520.txt").keys().contains("percent .txt"));
        assertTrue(resolver.resolve(DOMAIN + "/private.txt").localUrls().contains("private.txt"));
        for (String url : new String[]{DOMAIN.replace("localhost", "evil.example") + "/private.txt",
                DOMAIN + "-extra/private.txt", DOMAIN + "/%ff.txt", "https://localhost:8080/api/sys/common/static/private.txt"}) {
            assertTrue(resolver.resolve(url).localUrls().isEmpty());
        }
    }

    @Test public void administratorRetainsExistingImportPermission() {
        when(access.isAdministrator()).thenReturn(true);
        service.requireUse("private.txt");
        verifyZeroInteractions(downloads, files);
    }

    @Test public void rootRelativeConfiguredDomainUsesTheSameAuthorizationRule() {
        ReflectionTestUtils.setField(resolver, "staticDomain", "/api/sys/common/static");
        denied("<img src='/api/sys/common/static/%70rivate.txt'>");
        verify(downloads).status("private.txt");
        assertFalse(resolver.resolve("https://other.example/api/sys/common/static/private.txt").keys().contains("private.txt"));
    }
}
