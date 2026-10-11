package org.jeecg.workintegrity;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import org.apache.shiro.authz.UnauthorizedException;
import org.h2.jdbcx.JdbcDataSource;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.common.util.QiniuUtil;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.system.mapper.SysFileMapper;
import org.jeecg.modules.system.service.impl.SysFileServiceImpl;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.jeecg.modules.teaching.service.TeachingWorkAttachmentAccessService;
import org.jeecg.modules.teaching.service.TeachingWorkAttachmentService;
import org.jeecg.modules.teaching.mapper.TeachingWorkMapper;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.util.ReflectionUtils;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Actual H2 row locks and Spring commits, with JDBC-backed mapper adapters.
 * The production deletion and attachment guard execute unchanged. No sleep is
 * used to choose the vulnerable interleaving. */
public class FileDeletionConcurrencyTest {
    private JdbcTemplate jdbc;
    private DataSourceTransactionManager transactions;
    private SysFileServiceImpl files;
    private SysFileMapper mapper;
    private TeachingWorkAttachmentAccessService attachments;
    private QiniuUtil cloud;
    private Path root;
    private Path bytes;
    private ExecutorService threads;
    private CountDownLatch deletionContended;
    private AtomicBoolean failMark;
    private AtomicBoolean failRemove;

    @Before public void setup() throws Exception {
        JdbcDataSource data = new JdbcDataSource();
        data.setURL("jdbc:h2:mem:files_" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=5000");
        jdbc = new JdbcTemplate(data);
        transactions = new DataSourceTransactionManager(data);
        jdbc.execute("CREATE TABLE sys_file(id VARCHAR(64) PRIMARY KEY, file_path VARCHAR(255), file_location INT, create_by VARCHAR(64), del_flag INT)");
        jdbc.execute("CREATE TABLE teaching_work(id VARCHAR(64) PRIMARY KEY, work_file VARCHAR(64))");
        jdbc.update("INSERT INTO sys_file VALUES('file-a','attachment.txt',1,'owner',0)");
        root = Files.createTempDirectory("file-deletion-test-");
        bytes = root.resolve("attachment.txt");
        Files.write(bytes, "synthetic attachment".getBytes("UTF-8"));
        threads = Executors.newFixedThreadPool(2);
        failMark = new AtomicBoolean(); failRemove = new AtomicBoolean();
        files = new SysFileServiceImpl(); mapper = mock(SysFileMapper.class); cloud = mock(QiniuUtil.class);
        ReflectionTestUtils.setField(files, "baseMapper", mapper);
        ReflectionTestUtils.setField(files, "qiniuUtil", cloud);
        ReflectionTestUtils.setField(files, "uploadpath", root.toString());
        // Also runs against the pre-fix service to demonstrate the failed invariant.
        if (ReflectionUtils.findField(SysFileServiceImpl.class, "transactionManager") != null)
            ReflectionTestUtils.setField(files, "transactionManager", transactions);
        when(mapper.selectById(any())).thenAnswer(call -> read(false));
        when(mapper.selectOne(any())).thenAnswer(call -> {
            Wrapper<?> query = call.getArgument(0);
            boolean lock = query.getSqlSegment().contains("FOR UPDATE");
            if (lock && "deletion".equals(Thread.currentThread().getName()) && deletionContended != null)
                deletionContended.countDown();
            return read(lock);
        });
        when(mapper.referenceCount(any())).thenAnswer(call -> jdbc.queryForObject(
                "SELECT COUNT(*) FROM teaching_work WHERE work_file='file-a'", Integer.class));
        when(mapper.updateById(any())).thenAnswer(call -> {
            SysFile update = call.getArgument(0);
            int rows = jdbc.update("UPDATE sys_file SET del_flag=? WHERE id=?", update.getDelFlag(), update.getId());
            if (failMark.get()) throw new IllegalStateException("synthetic tombstone failure");
            return rows;
        });
        when(mapper.deleteById(any())).thenAnswer(call -> {
            if ("deletion".equals(Thread.currentThread().getName()) && deletionContended != null)
                deletionContended.countDown();
            if (failRemove.get()) throw new IllegalStateException("synthetic metadata cleanup failure");
            return jdbc.update("DELETE FROM sys_file WHERE id=?", (Object) call.getArgument(0));
        });
        attachments = new TeachingWorkAttachmentAccessService();
        TeachingAccessService access = mock(TeachingAccessService.class);
        LoginUser owner = new LoginUser(); owner.setId("owner-id"); owner.setUsername("owner");
        when(access.currentUser()).thenReturn(owner);
        ReflectionTestUtils.setField(attachments, "access", access);
        ReflectionTestUtils.setField(attachments, "files", files);
    }

    @After public void teardown() throws Exception {
        threads.shutdownNow(); threads.awaitTermination(5, TimeUnit.SECONDS);
        Files.deleteIfExists(bytes); Files.deleteIfExists(root);
    }

    private SysFile read(boolean lock) {
        return jdbc.query("SELECT * FROM sys_file WHERE id='file-a'" + (lock ? " FOR UPDATE" : ""),
                (row, n) -> new SysFile().setId(row.getString("id")).setFilePath(row.getString("file_path"))
                        .setFileLocation(row.getInt("file_location")).setCreateBy(row.getString("create_by"))
                        .setDelFlag(row.getInt("del_flag"))).stream().findFirst().orElse(null);
    }

    private void attach() {
        TeachingWork work = new TeachingWork(); work.setWorkFile("file-a");
        attachments.requireWrite(work, null);
        jdbc.update("INSERT INTO teaching_work VALUES('work-a','file-a')");
    }

    private static void await(CountDownLatch latch) {
        try { assertTrue("synchronization point was not reached", latch.await(4, TimeUnit.SECONDS)); }
        catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new AssertionError(error); }
    }

    @Test public void firstReferenceWinningTheLockPreservesBytesAndRejectsDeletion() throws Exception {
        CountDownLatch locked = new CountDownLatch(1), allowSave = new CountDownLatch(1);
        deletionContended = new CountDownLatch(1);
        Future<?> reference = threads.submit(() -> new TransactionTemplate(transactions).execute(status -> {
            TeachingWork work = new TeachingWork(); work.setWorkFile("file-a");
            attachments.requireWrite(work, null);
            locked.countDown(); await(allowSave);
            jdbc.update("INSERT INTO teaching_work VALUES('work-a','file-a')"); return null;
        }));
        await(locked);
        Future<Boolean> deletion = threads.submit(() -> {
            Thread.currentThread().setName("deletion"); return files.deleteWithFile("file-a");
        });
        try {
            // Old code reaches DELETE after erasing the bytes; fixed code reaches
            // SELECT FOR UPDATE before either the reference check or byte deletion.
            await(deletionContended);
            assertTrue("a held reference lock must protect the physical bytes", Files.exists(bytes));
        } finally { allowSave.countDown(); }
        reference.get(5, TimeUnit.SECONDS);
        assertFalse("the newly committed reference must prevent deletion", deletion.get(5, TimeUnit.SECONDS));
        assertTrue(Files.exists(bytes)); assertEquals(Integer.valueOf(0), read(false).getDelFlag());
        assertEquals(Integer.valueOf(1), jdbc.queryForObject("SELECT COUNT(*) FROM teaching_work", Integer.class));
    }

    @Test public void deletionWinningTheLockRejectsFirstReferenceAfterCommit() throws Exception {
        jdbc.update("UPDATE sys_file SET file_location=2");
        CountDownLatch cleanupEntered = new CountDownLatch(1), finishCleanup = new CountDownLatch(1);
        when(cloud.deleteFileByKey("attachment.txt")).thenAnswer(call -> {
            cleanupEntered.countDown(); await(finishCleanup); return true;
        });
        Future<Boolean> deletion = threads.submit(() -> files.deleteWithFile("file-a"));
        await(cleanupEntered);
        Future<Boolean> reference = threads.submit(() -> {
            try { new TransactionTemplate(transactions).execute(status -> { attach(); return null; }); return true; }
            catch (UnauthorizedException denied) { return false; }
        });
        finishCleanup.countDown();
        assertTrue(deletion.get(5, TimeUnit.SECONDS)); assertFalse(reference.get(5, TimeUnit.SECONDS));
        assertNull(read(false));
        assertEquals(Integer.valueOf(0), jdbc.queryForObject("SELECT COUNT(*) FROM teaching_work", Integer.class));
    }

    @Test public void failedPhysicalCleanupRetainsUnusableTombstoneAndRetryCompletes() {
        jdbc.update("UPDATE sys_file SET file_location=2");
        when(cloud.deleteFileByKey("attachment.txt")).thenReturn(false, true);
        assertFalse("failed physical deletion must not report success", files.deleteWithFile("file-a"));
        assertEquals(Integer.valueOf(1), read(false).getDelFlag());
        try { new TransactionTemplate(transactions).execute(status -> { attach(); return null; }); fail("tombstone must not be attachable"); }
        catch (UnauthorizedException expected) { }
        assertTrue(files.deleteWithFile("file-a")); assertNull(read(false));
    }

    @Test public void failedTombstoneTransactionNeverErasesBytes() {
        failMark.set(true);
        assertFalse(files.deleteWithFile("file-a"));
        assertTrue(Files.exists(bytes)); assertEquals(Integer.valueOf(0), read(false).getDelFlag());
    }

    @Test public void failedMetadataCleanupKeepsCommittedTombstoneForMissingObjectRetry() {
        failRemove.set(true);
        assertFalse(files.deleteWithFile("file-a"));
        assertFalse(Files.exists(bytes)); assertEquals(Integer.valueOf(1), read(false).getDelFlag());
        failRemove.set(false);
        assertTrue(files.deleteWithFile("file-a")); assertNull(read(false));
    }

    @Test public void successfulUnreferencedLocalDeleteRemovesBytesAndMetadata() {
        assertTrue(files.deleteWithFile("file-a")); assertFalse(Files.exists(bytes)); assertNull(read(false));
        assertTrue(files.deleteWithFile("file-a"));
    }

    @Test public void postCommitWorkCleanupCanNestItsReadTransactionWithoutSelfLocking() {
        TeachingWorkAttachmentService cleanup = new TeachingWorkAttachmentService();
        TeachingWorkMapper works = mock(TeachingWorkMapper.class);
        when(works.selectCount(any())).thenAnswer(call -> jdbc.queryForObject(
                "SELECT COUNT(*) FROM teaching_work WHERE work_file='file-a'", Integer.class));
        ReflectionTestUtils.setField(cleanup, "workMapper", works);
        ReflectionTestUtils.setField(cleanup, "fileService", files);
        ReflectionTestUtils.setField(cleanup, "transactionManager", transactions);
        jdbc.update("INSERT INTO teaching_work VALUES('work-a','file-a')");
        cleanup.cleanupAfterWorkDeletion("file-a");
        assertTrue(Files.exists(bytes)); assertNotNull(read(false));
        jdbc.update("DELETE FROM teaching_work WHERE id='work-a'");
        cleanup.cleanupAfterWorkDeletion("file-a");
        assertFalse(Files.exists(bytes)); assertNull(read(false));
    }
}
