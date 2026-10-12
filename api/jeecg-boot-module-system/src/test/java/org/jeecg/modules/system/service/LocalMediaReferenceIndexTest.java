package org.jeecg.modules.system.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.controller.LocalMediaReferenceController;
import org.jeecg.modules.system.entity.SysDataLog;
import org.jeecg.modules.system.mapper.SysDataLogMapper;
import org.jeecg.modules.system.service.impl.SysDataLogServiceImpl;
import org.jeecg.modules.teaching.entity.TeachingCourse;
import org.jeecg.modules.teaching.mapper.TeachingCourseMapper;
import org.jeecg.modules.teaching.mapper.TeachingWorkMapper;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.jeecg.modules.teaching.service.impl.TeachingCourseServiceImpl;
import org.junit.Before;
import org.junit.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.util.*;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class LocalMediaReferenceIndexTest {
    private static final String DOMAIN = "/api/sys/common/static";
    private LocalMediaReferenceIndex index;
    private JdbcTemplate jdbc;
    private LocalFileReferenceResolver resolver;
    private TestTransactions transactions;

    @Before public void setup() {
        jdbc = mock(JdbcTemplate.class);
        resolver = new LocalFileReferenceResolver();
        ReflectionTestUtils.setField(resolver, "json", new ObjectMapper());
        ReflectionTestUtils.setField(resolver, "staticDomain", DOMAIN);
        index = new LocalMediaReferenceIndex();
        transactions = new TestTransactions();
        ReflectionTestUtils.setField(index, "jdbc", jdbc);
        ReflectionTestUtils.setField(index, "json", new ObjectMapper());
        ReflectionTestUtils.setField(index, "resolver", resolver);
        ReflectionTestUtils.setField(index, "transactionManager", transactions);
        ReflectionTestUtils.setField(index, "staticDomain", DOMAIN);
        when(jdbc.queryForMap(anyString())).thenReturn(row("version", 1, "static_domain", DOMAIN));
    }

    @Test public void plainHtmlAndJsonReferencesKeepExactOnceDecodedKeys() {
        Map<String, Set<String>> found = index.references(LocalMediaSource.COURSE, row(
                "course_icon", "raw/a+b.png",
                "course_cover", DOMAIN + "/%e4%bd%9c%20%2b.png",
                "course_desc", "<img src='" + DOMAIN + "/&#x70;ercent%2520.png'>",
                "course_map", "{\"nested\":[{\"src\":\"" + DOMAIN + "/json%2B.png\"}]}"));
        assertTrue(found.get("course_icon").contains("raw/a+b.png"));
        assertTrue(found.get("course_cover").contains("作 +.png"));
        assertTrue(found.get("course_desc").contains("percent%20.png"));
        assertFalse(found.get("course_desc").contains("percent .png"));
        assertTrue(found.get("course_map").contains("json+.png"));
    }

    @Test public void invalidUtf8ForeignOriginsAndTraversalCannotCreateDownloadKeys() {
        for (String value : Arrays.asList(DOMAIN + "/%ff.png", "https://foreign.invalid" + DOMAIN + "/a.png", "../a.png")) {
            Set<String> found = index.references(LocalMediaSource.NEWS, row("news_content", value)).get("news_content");
            assertTrue(found.isEmpty());
        }
    }

    @Test public void historyUsesOnlyTeachingWorkTopLevelAttachmentIds() {
        Map<String, Object> history = row("data_table", "teaching_work", "data_content",
                "{\"workFile\":\"private-id\",\"workName\":\"unrelated-id\",\"nested\":{\"workCover\":\"nested-id\"}}");
        assertEquals(Collections.singleton("private-id"), index.references(LocalMediaSource.HISTORY, history).get("workFile"));
        assertEquals(1, index.references(LocalMediaSource.HISTORY, history).size());
        history.put("data_table", "other_module");
        assertTrue(index.references(LocalMediaSource.HISTORY, history).isEmpty());
        history.put("data_table", "teaching_work"); history.put("data_content", "{broken");
        assertTrue(index.references(LocalMediaSource.HISTORY, history).isEmpty());
    }

    @Test public void digestNeverNormalizesCaseOrUnicode() {
        assertNotEquals(LocalMediaReferenceIndex.hash("A.png"), LocalMediaReferenceIndex.hash("a.png"));
        assertNotEquals(LocalMediaReferenceIndex.hash("é.png"), LocalMediaReferenceIndex.hash("e\u0301.png"));
        assertEquals(64, LocalMediaReferenceIndex.hash("作业.png").length());
    }

    @Test public void readyBootDoesNotScanOrRewriteContent() {
        index.initialize();
        verify(jdbc).queryForMap("SELECT version,static_domain FROM sys_local_file_reference_state WHERE id=1 FOR UPDATE");
        verifyNoMoreInteractions(jdbc);
        assertEquals(1, transactions.commits);
    }

    @Test public void changedDomainFailsBeforeAnyIndexMutation() {
        when(jdbc.queryForMap(anyString())).thenReturn(row("version", 1, "static_domain", "https://old.invalid/static"));
        try { index.initialize(); fail("configuration drift must require explicit rebuild"); }
        catch (IllegalStateException expected) { }
        verify(jdbc, never()).update(anyString());
        assertEquals(1, transactions.rollbacks);
    }

    @Test public void initializationFailureRollsBackAndNeverMarksReady() {
        when(jdbc.queryForMap(anyString())).thenReturn(row("version", 0, "static_domain", null));
        when(jdbc.queryForList(startsWith("SELECT * FROM teaching_course "))).thenThrow(new DataIntegrityViolationException("fixture"));
        try { index.initialize(); fail("failed scan must not complete initialization"); }
        catch (DataIntegrityViolationException expected) { }
        verify(jdbc, never()).update(startsWith("UPDATE sys_local_file_reference_state"), anyInt(), anyString());
        assertEquals(1, transactions.rollbacks);
    }

    @Test public void unknownVersionNeverDowngradesEvenDuringExplicitRebuild() {
        when(jdbc.queryForMap(anyString())).thenReturn(row("version", 2, "static_domain", DOMAIN));
        for (boolean force : Arrays.asList(false, true)) {
            try { index.rebuild(force); fail("unknown format must not be rewritten"); }
            catch (IllegalStateException expected) { }
        }
        verify(jdbc, never()).update(anyString());
        assertEquals(2, transactions.rollbacks);
    }

    @Test public void mutationWithoutBusinessTransactionIsRejected() {
        try { index.replace(LocalMediaSource.COURSE, "a"); fail("no transaction"); }
        catch (IllegalStateException expected) { }
        verifyZeroInteractions(jdbc);
    }

    @Test public void partialEditIndexesPersistedFullRowAndSharesTransaction() {
        TeachingCourseMapper mapper = mock(TeachingCourseMapper.class);
        TeachingCourseServiceImpl service = new TeachingCourseServiceImpl();
        ReflectionTestUtils.setField(service, "baseMapper", mapper);
        ReflectionTestUtils.setField(service, "mediaIndex", index);
        when(mapper.updateById(any())).thenAnswer(call -> {
            assertTrue(TransactionSynchronizationManager.isActualTransactionActive());
            return 1;
        });
        when(jdbc.queryForList("SELECT * FROM teaching_course WHERE id=? FOR UPDATE", "course-a"))
                .thenReturn(Collections.singletonList(row("id", "course-a", "course_cover", "kept.png")));
        assertTrue(service.updateById(new TeachingCourse().setId("course-a").setCourseName("renamed")));
        verify(jdbc).update(startsWith("INSERT INTO sys_local_file_reference "), eq("teaching_course"), eq("course-a"), eq("course_cover"), eq("key"), eq(LocalMediaReferenceIndex.hash("kept.png")), eq("kept.png"));
        assertEquals(1, transactions.commits);
    }

    @Test public void existingWorkHistoryEntryUsesItsMappedSourceAndIndexesInsideTheTransaction() {
        SysDataLogMapper mapper = mock(SysDataLogMapper.class);
        SysDataLogServiceImpl service = new SysDataLogServiceImpl();
        ReflectionTestUtils.setField(service, "baseMapper", mapper);
        ReflectionTestUtils.setField(service, "logMapper", mapper);
        ReflectionTestUtils.setField(service, "mediaIndex", index);
        when(mapper.insert(any())).thenAnswer(call -> {
            assertTrue(TransactionSynchronizationManager.isActualTransactionActive());
            ((SysDataLog) call.getArgument(0)).setId("history-a");
            return 1;
        });
        String previous = "{\"workFile\":\"previous-file\"}";
        when(jdbc.queryForList("SELECT * FROM sys_data_log WHERE id=? FOR UPDATE", "history-a"))
                .thenReturn(Collections.singletonList(row("id", "history-a", "data_table", "teaching_work", "data_content", previous)));
        service.addDataLog("teaching_work", "existing-work", previous);
        verify(jdbc).update(startsWith("INSERT INTO sys_local_file_reference "), eq("sys_data_log"), eq("history-a"), eq("workFile"), eq("file"), eq(LocalMediaReferenceIndex.hash("previous-file")), eq("previous-file"));
        assertEquals(1, transactions.commits);
    }

    @Test public void indexFaultAbortsTheSameBusinessTransaction() {
        TeachingCourseMapper mapper = mock(TeachingCourseMapper.class);
        TeachingCourseServiceImpl service = new TeachingCourseServiceImpl();
        ReflectionTestUtils.setField(service, "baseMapper", mapper);
        ReflectionTestUtils.setField(service, "mediaIndex", index);
        when(mapper.updateById(any())).thenReturn(1);
        when(jdbc.queryForList("SELECT * FROM teaching_course WHERE id=? FOR UPDATE", "course-a"))
                .thenReturn(Collections.singletonList(row("id", "course-a", "course_cover", "next.png")));
        doThrow(new DataIntegrityViolationException("index fixture fault")).when(jdbc).update(
                startsWith("INSERT INTO sys_local_file_reference "), anyString(), anyString(), anyString(), anyString(), anyString(), anyString());
        try { service.updateById(new TeachingCourse().setId("course-a")); fail("index error must propagate"); }
        catch (DataIntegrityViolationException expected) { }
        assertEquals(1, transactions.rollbacks);
        assertEquals(0, transactions.commits);
    }

    @Test public void hashCandidateWithDifferentFullValueNeverLoadsSource() {
        when(jdbc.queryForList(startsWith("SELECT source_type"), eq("key"), anyString()))
                .thenReturn(Collections.singletonList(row("source_type", "teaching_course", "source_id", "other", "reference_value", "UPPER.png")));
        assertTrue(index.candidates("key", Collections.singleton("upper.png")).isEmpty());
        verify(jdbc, never()).queryForList(startsWith("SELECT * FROM"), any(Object[].class));
    }

    @Test public void staleIndexDoesNotPublishRemovedOrUnpublishedContent() {
        LocalMediaReferenceIndex lookup = mock(LocalMediaReferenceIndex.class);
        LocalDownloadAccessService downloads = new LocalDownloadAccessService();
        TeachingAccessService access = mock(TeachingAccessService.class);
        ReflectionTestUtils.setField(downloads, "access", access);
        ReflectionTestUtils.setField(downloads, "files", mock(ISysFileService.class));
        ReflectionTestUtils.setField(downloads, "works", mock(TeachingWorkMapper.class));
        ReflectionTestUtils.setField(downloads, "references", resolver);
        ReflectionTestUtils.setField(downloads, "mediaIndex", lookup);
        Map<LocalMediaSource, List<Map<String, Object>>> sources = new EnumMap<>(LocalMediaSource.class);
        sources.put(LocalMediaSource.NEWS, Collections.singletonList(row("news_status", 1, "news_content", "changed.png")));
        when(lookup.candidates(eq("key"), anyCollection())).thenReturn(sources);
        assertEquals(401, downloads.status("old.png"));
        sources.put(LocalMediaSource.NEWS, Collections.singletonList(row("news_status", 0, "news_content", "old.png")));
        assertEquals(401, downloads.status("old.png"));
        sources.put(LocalMediaSource.NEWS, Collections.singletonList(row("news_status", 1, "news_content", "old.png")));
        assertEquals(200, downloads.status("old.png"));
    }

    @Test public void ordinaryUsersCannotRebuildAndAdministratorCan() {
        LocalMediaReferenceController controller = new LocalMediaReferenceController();
        LocalMediaReferenceIndex lookup = mock(LocalMediaReferenceIndex.class);
        TeachingAccessService access = mock(TeachingAccessService.class);
        ReflectionTestUtils.setField(controller, "access", access);
        ReflectionTestUtils.setField(controller, "index", lookup);
        for (LoginUser user : Arrays.asList(null, new LoginUser())) {
            when(access.currentUser()).thenReturn(user);
            try { controller.rebuild(); fail("not administrator"); }
            catch (UnauthorizedException expected) { }
        }
        verifyZeroInteractions(lookup);
        when(access.isAdministrator()).thenReturn(true);
        assertTrue(controller.rebuild().isSuccess());
        verify(lookup).rebuild(true);
    }

    private static Map<String, Object> row(Object... values) {
        Map<String, Object> row = new LinkedHashMap<>();
        for (int i = 0; i < values.length; i += 2) row.put((String) values[i], values[i + 1]);
        return row;
    }
    private static class TestTransactions extends AbstractPlatformTransactionManager {
        int commits, rollbacks;
        protected Object doGetTransaction() { return new Object(); }
        protected boolean isExistingTransaction(Object transaction) { return TransactionSynchronizationManager.isActualTransactionActive(); }
        protected void doBegin(Object transaction, TransactionDefinition definition) { }
        protected void doCommit(DefaultTransactionStatus status) { commits++; }
        protected void doRollback(DefaultTransactionStatus status) { rollbacks++; }
    }
}
