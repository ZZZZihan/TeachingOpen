package org.jeecg.audit;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.reflect.MethodSignature;
import org.h2.jdbcx.JdbcDataSource;
import org.jeecg.common.aspect.annotation.AutoLog;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.aspect.AutoLogAspect;
import org.jeecg.modules.system.entity.SysLog;
import org.jeecg.modules.system.service.AutoLogWriter;
import org.jeecg.modules.system.service.ISysLogService;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.slf4j.LoggerFactory;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.util.UUID;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class AutoLogSafetyTest {
    private AutoLogAspect aspect;
    private AutoLogWriter writer;
    private ProceedingJoinPoint point;
    private MethodSignature signature;
    private MockHttpServletRequest request;
    private Logger logger;
    private ListAppender<ILoggingEvent> warnings;
    private final Object result = new Object();

    public static class Endpoint {
        @AutoLog("synthetic operation")
        public Object edit(Object sensitiveBody) { return null; }
    }

    @Before public void setup() throws Throwable {
        aspect = new AutoLogAspect();
        writer = mock(AutoLogWriter.class);
        ReflectionTestUtils.setField(aspect, "auditWriter", writer);
        point = mock(ProceedingJoinPoint.class);
        signature = mock(MethodSignature.class);
        when(point.getSignature()).thenReturn(signature);
        when(signature.getMethod()).thenReturn(Endpoint.class.getMethod("edit", Object.class));
        when(signature.getName()).thenReturn("edit");
        when(signature.getDeclaringTypeName()).thenReturn(Endpoint.class.getName());
        when(point.proceed()).thenReturn(result);
        when(point.getArgs()).thenThrow(new AssertionError("Request arguments must never be read or serialized"));
        request = new MockHttpServletRequest("PUT", "/synthetic/edit");
        request.setRemoteAddr("127.0.0.1");
        request.setQueryString("token=private-query&comment=private-feedback");
        request.addHeader("Authorization", "Bearer private-credential");
        request.addHeader("X-Forwarded-For", "untrusted-header-canary");
        request.setContent("{\"password\":\"private-body\",\"comment\":\"private-feedback\"}".getBytes("UTF-8"));
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
        LoginUser identity = new LoginUser(); identity.setUsername("synthetic-user"); identity.setRealname("Synthetic User");
        Subject subject = mock(Subject.class); when(subject.getPrincipal()).thenReturn(identity); ThreadContext.bind(subject);
        logger = (Logger) LoggerFactory.getLogger(AutoLogAspect.class);
        warnings = new ListAppender<>(); warnings.start(); logger.addAppender(warnings);
    }

    @After public void cleanup() {
        logger.detachAppender(warnings); warnings.stop();
        ThreadContext.unbindSubject(); RequestContextHolder.resetRequestAttributes();
    }

    @Test public void metadataDoesNotReadOrCopyArgumentsForAnyHttpMethod() throws Throwable {
        for (String verb : new String[]{"GET", "POST", "PUT", "PATCH", "DELETE"}) {
            request.setMethod(verb);
            assertSame(result, aspect.around(point));
        }
        ArgumentCaptor<SysLog> entries = ArgumentCaptor.forClass(SysLog.class);
        verify(writer, times(5)).save(entries.capture());
        for (SysLog entry : entries.getAllValues()) {
            assertNull(entry.getRequestParam()); assertNull(entry.getRequestUrl());
            assertEquals("synthetic operation", entry.getLogContent());
            assertEquals(Endpoint.class.getName() + ".edit()", entry.getMethod());
            assertEquals(Integer.valueOf(2), entry.getLogType()); assertEquals(Integer.valueOf(3), entry.getOperateType());
            assertEquals("synthetic-user", entry.getUserid()); assertEquals("Synthetic User", entry.getUsername());
            assertEquals("127.0.0.1", entry.getIp()); assertNotNull(entry.getRequestType());
            assertNotNull(entry.getCreateTime()); assertNotNull(entry.getCostTime());
            assertFalse(entry.toString().contains("private-")); assertFalse(entry.toString().contains("untrusted-header"));
        }
        verify(point, never()).getArgs(); assertTrue(warnings.list.isEmpty());
    }

    @Test public void auditExceptionPreservesOriginalResponseAndProducesSanitizedWarning() throws Throwable {
        doThrow(new IllegalStateException("private-password=secret private-feedback=grade")).when(writer).save(any());
        assertSame(result, aspect.around(point));
        verify(point, times(1)).proceed(); verify(writer, times(1)).save(any());
        assertEquals(1, warnings.list.size());
        ILoggingEvent warning = warnings.list.get(0);
        assertEquals(Level.WARN, warning.getLevel()); assertNull(warning.getThrowableProxy());
        assertEquals("audit_write_failed method=" + Endpoint.class.getName() + ".edit() failureType=java.lang.IllegalStateException", warning.getFormattedMessage());
        assertFalse(warning.getFormattedMessage().contains("private-"));
    }

    @Test public void auditContextFailureDoesNotChangeBusinessResponse() throws Throwable {
        RequestContextHolder.resetRequestAttributes();
        assertSame(result, aspect.around(point));
        verifyZeroInteractions(writer); verify(point, times(1)).proceed();
        assertEquals(1, warnings.list.size()); assertNull(warnings.list.get(0).getThrowableProxy());
    }

    @Test public void businessFailurePropagatesUnchangedWithoutRunningAudit() throws Throwable {
        IllegalStateException businessFailure = new IllegalStateException("business failed");
        when(point.proceed()).thenThrow(businessFailure);
        try { aspect.around(point); fail("Business error must propagate"); }
        catch (IllegalStateException actual) { assertSame(businessFailure, actual); }
        verifyZeroInteractions(writer); assertTrue(warnings.list.isEmpty()); verify(point, times(1)).proceed();
    }

    @Test public void falseAuditSaveIsObservableAndCannotAlterBusinessResponse() throws Throwable {
        AutoLogWriter target = new AutoLogWriter();
        ISysLogService logs = mock(ISysLogService.class); when(logs.save(any())).thenReturn(false);
        ReflectionTestUtils.setField(target, "sysLogService", logs); ReflectionTestUtils.setField(aspect, "auditWriter", target);
        assertSame(result, aspect.around(point));
        verify(logs, times(1)).save(any()); assertEquals(1, warnings.list.size());
    }

    @Test public void realSqlAuditFailureCannotMarkAnOuterBusinessTransactionRollbackOnly() throws Throwable {
        JdbcDataSource data = new JdbcDataSource();
        data.setURL("jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
        JdbcTemplate jdbc = new JdbcTemplate(data);
        jdbc.execute("CREATE TABLE business_write(id INT PRIMARY KEY)");
        jdbc.execute("CREATE TABLE audit_entry(id INT PRIMARY KEY, accepted BOOLEAN CHECK(accepted=TRUE))");
        DataSourceTransactionManager manager = new DataSourceTransactionManager(data);
        ISysLogService logs = mock(ISysLogService.class);
        when(logs.save(any())).thenAnswer(call -> { jdbc.update("INSERT INTO audit_entry VALUES(1,FALSE)"); return true; });
        AutoLogWriter target = new AutoLogWriter(); ReflectionTestUtils.setField(target, "sysLogService", logs);
        ProxyFactory factory = new ProxyFactory(target);
        factory.addAdvice(new TransactionInterceptor(manager, new AnnotationTransactionAttributeSource()));
        ReflectionTestUtils.setField(aspect, "auditWriter", factory.getProxy());
        when(point.proceed()).thenAnswer(call -> { jdbc.update("INSERT INTO business_write VALUES(1)"); return result; });
        Object returned = new TransactionTemplate(manager).execute(status -> {
            try { return aspect.around(point); } catch (Throwable failure) { throw new AssertionError(failure); }
        });
        assertSame(result, returned);
        assertEquals(Integer.valueOf(1), jdbc.queryForObject("SELECT COUNT(*) FROM business_write", Integer.class));
        assertEquals(Integer.valueOf(0), jdbc.queryForObject("SELECT COUNT(*) FROM audit_entry", Integer.class));
        verify(point, times(1)).proceed(); verify(logs, times(1)).save(any()); assertEquals(1, warnings.list.size());
    }
}
