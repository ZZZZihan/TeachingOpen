package org.jeecg.additionalwork;

import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.BoundSql;
import org.apache.ibatis.session.Configuration;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.service.ISysDepartService;
import org.jeecg.modules.teaching.entity.TeachingDepartDayLog;
import org.jeecg.modules.teaching.enums.DepartDayLogType;
import org.jeecg.modules.teaching.mapper.TeachingDepartDayLogMapper;
import org.jeecg.modules.teaching.service.impl.TeachingDepartDayLogServiceImpl;
import org.junit.Before;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.test.util.ReflectionTestUtils;

import java.io.InputStream;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class AdditionalWorkStatisticsTest {
    private TeachingDepartDayLogServiceImpl service;
    private TeachingDepartDayLogMapper logs;
    private ISysDepartService departments;

    @Before public void setup() {
        service = new TeachingDepartDayLogServiceImpl();
        logs = mock(TeachingDepartDayLogMapper.class);
        departments = mock(ISysDepartService.class);
        ReflectionTestUtils.setField(service, "baseMapper", logs);
        ReflectionTestUtils.setField(service, "sysDepartService", departments);
        SysDepart department = new SysDepart();
        department.setId("class-a"); department.setDepartName("合成班级"); department.setDelFlag("0");
        when(departments.getOne(any())).thenReturn(department);
        when(logs.selectDayIdForUpdate(eq("class-a"), anyString())).thenReturn("current-day");
        when(logs.incrementDayCounter(eq("current-day"), eq("class-a"), anyString(), eq("ADDITIONAL_WORK_ASSIGN_COUNT"))).thenReturn(1);
        when(logs.insert(any())).thenReturn(1);
    }

    @Test public void existingDayUsesCurrentReadAndAtomicIncrementAfterDepartmentLock() {
        service.recordAdditionalWorkAssignment("class-a");
        InOrder order = inOrder(departments, logs);
        order.verify(departments).getOne(any());
        order.verify(logs).selectDayIdForUpdate(eq("class-a"), anyString());
        order.verify(logs).incrementDayCounter(eq("current-day"), eq("class-a"), anyString(), eq("ADDITIONAL_WORK_ASSIGN_COUNT"));
        verify(logs, never()).insert(any());
        verify(logs, never()).updateById(any());
        verify(logs, never()).selectList(any());
    }

    @Test public void firstDayCreatesOneInitializedRowAfterCurrentRead() {
        when(logs.selectDayIdForUpdate(eq("class-a"), anyString())).thenReturn(null);
        service.recordAdditionalWorkAssignment("class-a");
        ArgumentCaptor<TeachingDepartDayLog> capture = ArgumentCaptor.forClass(TeachingDepartDayLog.class);
        verify(logs).insert(capture.capture());
        TeachingDepartDayLog inserted = capture.getValue();
        assertEquals("class-a", inserted.getDepartId()); assertEquals("合成班级", inserted.getDepartName());
        assertEquals(Integer.valueOf(1), inserted.getAdditionalWorkAssignCount());
        assertEquals(Integer.valueOf(0), inserted.getUnitOpenCount());
        assertEquals(Integer.valueOf(0), inserted.getCourseWorkAssignCount());
        assertEquals(Integer.valueOf(0), inserted.getCourseWorkCorrectCount());
        assertEquals(Integer.valueOf(0), inserted.getCourseWorkSubmitCount());
        assertEquals(Integer.valueOf(0), inserted.getAdditionalWorkCorrectCount());
        assertEquals(Integer.valueOf(0), inserted.getAdditionalWorkSubmitCount());
        assertNotNull(inserted.getCreateTime());
        verify(logs, never()).incrementDayCounter(anyString(), anyString(), anyString(), anyString());
    }

    @Test(expected = JeecgBootException.class) public void zeroUpdatedRowsAbortTheTaskTransaction() {
        when(logs.incrementDayCounter(eq("current-day"), eq("class-a"), anyString(), eq("ADDITIONAL_WORK_ASSIGN_COUNT"))).thenReturn(0);
        service.recordAdditionalWorkAssignment("class-a");
    }

    @Test(expected = JeecgBootException.class) public void zeroInsertedRowsAbortTheTaskTransaction() {
        when(logs.selectDayIdForUpdate(eq("class-a"), anyString())).thenReturn(null);
        when(logs.insert(any())).thenReturn(0);
        service.recordAdditionalWorkAssignment("class-a");
    }

    @Test public void missingDepartmentCannotCreateStatistics() {
        when(departments.getOne(any())).thenReturn(null);
        try { service.recordAdditionalWorkAssignment("class-a"); fail("missing class must fail"); }
        catch (JeecgBootException expected) { }
        verifyZeroInteractions(logs);
    }

    @Test public void everyEventInitializesOnlyItsOwnCounter() {
        when(logs.selectDayIdForUpdate(eq("class-a"), anyString())).thenReturn(null);
        for (DepartDayLogType type : DepartDayLogType.values()) service.addLog("class-a", type);
        ArgumentCaptor<TeachingDepartDayLog> capture = ArgumentCaptor.forClass(TeachingDepartDayLog.class);
        verify(logs, times(7)).insert(capture.capture());
        List<TeachingDepartDayLog> inserted = capture.getAllValues();
        for (int event = 0; event < 7; event++) {
            TeachingDepartDayLog log = inserted.get(event);
            List<Integer> counts = Arrays.asList(log.getUnitOpenCount(), log.getCourseWorkAssignCount(),
                    log.getAdditionalWorkAssignCount(), log.getCourseWorkSubmitCount(), log.getAdditionalWorkSubmitCount(),
                    log.getCourseWorkCorrectCount(), log.getAdditionalWorkCorrectCount());
            for (int counter = 0; counter < 7; counter++) {
                assertEquals("only " + DepartDayLogType.values()[event] + " should increment",
                        Integer.valueOf(event == counter ? 1 : 0), counts.get(counter));
            }
        }
        verify(logs, never()).incrementDayCounter(anyString(), anyString(), anyString(), anyString());
    }

    @Test public void everyEventUsesItsOwnAtomicIncrementWithoutWritingAnEntity() {
        when(logs.incrementDayCounter(anyString(), anyString(), anyString(), anyString())).thenReturn(1);
        for (DepartDayLogType type : DepartDayLogType.values()) {
            service.addLog("class-a", type);
            verify(logs).incrementDayCounter(eq("current-day"), eq("class-a"), anyString(), eq(type.name()));
        }
        verify(departments, times(7)).getOne(any());
        verify(logs, times(7)).selectDayIdForUpdate(eq("class-a"), anyString());
        verify(logs, never()).insert(any());
        verify(logs, never()).updateById(any());
        verify(logs, never()).selectList(any());
    }

    @Test public void nullEventIsRejectedBeforeAnyDatabaseAccess() {
        try { service.addLog("class-a", null); fail("null event must fail"); }
        catch (JeecgBootException expected) { }
        verifyZeroInteractions(departments, logs);
    }

    @Test public void nonSingleUpdateCountsAbortEveryEvent() {
        for (int rows : new int[] {0, 2}) {
            when(logs.incrementDayCounter(anyString(), anyString(), anyString(), anyString())).thenReturn(rows);
            for (DepartDayLogType type : DepartDayLogType.values()) {
                try { service.addLog("class-a", type); fail("unexpected affected rows must fail: " + type); }
                catch (JeecgBootException expected) { }
            }
        }
        verify(logs, never()).insert(any());
        verify(logs, never()).updateById(any());
    }

    @Test public void actualMapperSqlHasOneNullSafeAtomicTargetAndBindsUntrustedValues() throws Exception {
        String resource = "org/jeecg/modules/teaching/mapper/xml/TeachingDepartDayLogMapper.xml";
        Configuration configuration = new Configuration();
        try (InputStream xml = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertNotNull("production mapper XML must be tested", xml);
            new XMLMapperBuilder(xml, configuration, resource, configuration.getSqlFragments()).parse();
        }
        String namespace = TeachingDepartDayLogMapper.class.getName() + ".";
        Map<String, Object> parameters = new HashMap<>();
        parameters.put("id", "current-day"); parameters.put("departId", "class-a"); parameters.put("day", "2026-10-10");
        for (DepartDayLogType type : DepartDayLogType.values()) {
            parameters.put("counter", type.name());
            BoundSql bound = configuration.getMappedStatement(namespace + "incrementDayCounter").getBoundSql(parameters);
            String sql = bound.getSql().replaceAll("\\s+", " ").trim();
            String column = type.name().toLowerCase(java.util.Locale.ROOT);
            assertEquals("UPDATE teaching_depart_day_log SET " + column + " = COALESCE(" + column + ", 0) + 1",
                    sql.substring(0, sql.indexOf(" WHERE")));
            assertTrue(sql.contains("WHERE id = ? AND depart_id = ? AND create_time = ?"));
            assertEquals(4, bound.getParameterMappings().size());
        }
        parameters.put("counter", "additional_work_assign_count=0,unit_open_count");
        String invalid = configuration.getMappedStatement(namespace + "incrementDayCounter").getBoundSql(parameters).getSql();
        assertTrue(invalid.contains("id = id"));
        assertFalse(invalid.contains((String) parameters.get("counter")));
        assertTrue(invalid.contains("AND ? IN"));
        parameters.put("counter", null);
        assertTrue(configuration.getMappedStatement(namespace + "incrementDayCounter").getBoundSql(parameters).getSql().contains("id = id"));
        String current = configuration.getMappedStatement(namespace + "selectDayIdForUpdate").getBoundSql(parameters).getSql();
        assertTrue(current.contains("FOR UPDATE"));
    }
}
