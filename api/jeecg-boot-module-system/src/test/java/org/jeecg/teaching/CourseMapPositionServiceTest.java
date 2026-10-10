package org.jeecg.teaching;

import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.modules.teaching.mapper.TeachingCourseUnitMapper;
import org.jeecg.modules.teaching.controller.TeachingCourseUnitController;
import org.jeecg.modules.teaching.entity.TeachingCourseUnit;
import org.jeecg.modules.teaching.model.CourseMapUpdateRequest;
import org.jeecg.modules.teaching.service.ITeachingCourseUnitService;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.jeecg.modules.teaching.service.impl.TeachingCourseUnitServiceImpl;
import org.junit.Before;
import org.junit.Test;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;

import java.io.InputStream;
import java.util.*;
import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Real service and Spring transaction interceptor; persistence is a controlled test double. */
public class CourseMapPositionServiceTest {
    private TeachingCourseUnitMapper mapper;
    private TeachingAccessService access;
    private ITeachingCourseUnitService service;
    private Map<String, List<Integer>> coordinates;
    private SnapshotTransactions transactions;

    @Before public void setup() {
        mapper = mock(TeachingCourseUnitMapper.class);
        access = mock(TeachingAccessService.class);
        when(access.isAdministrator()).thenReturn(true);
        coordinates = new HashMap<>();
        coordinates.put("a1", Arrays.asList(1, 2));
        coordinates.put("a2", Arrays.asList(3, 4));
        transactions = new SnapshotTransactions(coordinates);
        when(mapper.lockMapUnits(eq("A"), anySet())).thenAnswer(call -> {
            Set<String> requested = call.getArgument(1);
            List<String> matched = new ArrayList<>();
            for (String id : requested) if (coordinates.containsKey(id)) matched.add(id);
            return matched;
        });
        when(mapper.updateMapPosition(eq("A"), anyString(), anyInt(), anyInt())).thenAnswer(call -> {
            coordinates.put(call.getArgument(1), Arrays.asList(call.getArgument(2), call.getArgument(3)));
            return 1;
        });
        TeachingCourseUnitServiceImpl target = new TeachingCourseUnitServiceImpl();
        ReflectionTestUtils.setField(target, "baseMapper", mapper);
        ReflectionTestUtils.setField(target, "teachingAccessService", access);
        ProxyFactory factory = new ProxyFactory(target);
        factory.addAdvice(new TransactionInterceptor(transactions, new AnnotationTransactionAttributeSource()));
        service = (ITeachingCourseUnitService) factory.getProxy();
    }
    private CourseMapUpdateRequest request(String... ids) {
        CourseMapUpdateRequest request = new CourseMapUpdateRequest(); request.setCourseId("A");
        List<CourseMapUpdateRequest.UnitPosition> units = new ArrayList<>();
        for (String id : ids) {
            CourseMapUpdateRequest.UnitPosition unit = new CourseMapUpdateRequest.UnitPosition();
            unit.setId(id); unit.setMapX(8); unit.setMapY(9); units.add(unit);
        }
        request.setUnits(units); return request;
    }
    private void invalid(CourseMapUpdateRequest request) {
        try { service.updateMapPositions(request); fail("must reject invalid request"); }
        catch (IllegalArgumentException expected) { }
    }
    @Test public void validatesCompleteBatchBeforeAnyWrite() {
        invalid(null); invalid(request()); invalid(request("a1", "a1"));
        CourseMapUpdateRequest missingCoordinate = request("a1", "a2");
        missingCoordinate.getUnits().get(1).setMapY(null); invalid(missingCoordinate);
        verifyZeroInteractions(mapper);
        assertEquals(Arrays.asList(1, 2), coordinates.get("a1"));
    }
    @Test public void deniedRoleAndCourseNeverReachPersistence() {
        when(access.isAdministrator()).thenReturn(false);
        try { service.updateMapPositions(request("a1")); fail("student must be rejected"); }
        catch (UnauthorizedException expected) { }
        when(access.isAdministrator()).thenReturn(true);
        doThrow(new UnauthorizedException("denied")).when(access).requireCourse("A");
        try { service.updateMapPositions(request("a1")); fail("course denial must propagate"); }
        catch (UnauthorizedException expected) { }
        verifyZeroInteractions(mapper);
    }
    @Test public void missingOrOtherCourseUnitRejectsWholeBatch() {
        assertFalse(service.updateMapPositions(request("a1", "b1")));
        verify(mapper, never()).updateMapPosition(anyString(), anyString(), anyInt(), anyInt());
        assertEquals(Arrays.asList(1, 2), coordinates.get("a1"));
    }
    @Test public void successfulBatchChangesOnlyRequestedPositions() {
        assertTrue(service.updateMapPositions(request("a1", "a2")));
        assertEquals(Arrays.asList(8, 9), coordinates.get("a1"));
        assertEquals(Arrays.asList(8, 9), coordinates.get("a2"));
        verify(mapper).lockMapUnits(eq("A"), eq(new HashSet<>(Arrays.asList("a1", "a2"))));
        verify(access).requireCourse("A");
        assertEquals(1, transactions.commits); assertEquals(0, transactions.rollbacks);
    }
    @Test public void failedSecondWriteRollsBackFirstUsingRealSpringTransactionAdvice() {
        doReturn(0).when(mapper).updateMapPosition("A", "a2", 8, 9);
        assertFalse(service.updateMapPositions(request("a1", "a2")));
        assertEquals(Arrays.asList(1, 2), coordinates.get("a1"));
        assertEquals(Arrays.asList(3, 4), coordinates.get("a2"));
        assertEquals(0, transactions.commits); assertEquals(1, transactions.rollbacks);
    }
    @Test public void mapperExceptionRollsBackEveryEarlierPosition() {
        doThrow(new IllegalStateException("synthetic write failure")).when(mapper).updateMapPosition("A", "a2", 8, 9);
        try { service.updateMapPositions(request("a1", "a2")); fail("write failure must propagate"); }
        catch (IllegalStateException expected) { }
        assertEquals(Arrays.asList(1, 2), coordinates.get("a1"));
        assertEquals(Arrays.asList(3, 4), coordinates.get("a2"));
        assertEquals(1, transactions.rollbacks);
    }
    @Test public void actualMybatisStatementBindsOnlyCoordinatesAndConstrainsCourseAndActiveUnit() throws Exception {
        String resource = "org/jeecg/modules/teaching/mapper/xml/TeachingCourseUnitMapper.xml";
        Configuration configuration = new Configuration();
        try (InputStream input = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertNotNull("mapper XML must be packaged", input);
            new XMLMapperBuilder(input, configuration, resource, configuration.getSqlFragments()).parse();
        }
        Map<String, Object> parameters = new HashMap<>();
        parameters.put("courseId", "A"); parameters.put("unitId", "a1"); parameters.put("mapX", 8); parameters.put("mapY", 9);
        String sql = configuration.getMappedStatement("org.jeecg.modules.teaching.mapper.TeachingCourseUnitMapper.updateMapPosition")
                .getBoundSql(parameters).getSql().replaceAll("\\s+", " ").trim();
        assertEquals("UPDATE teaching_course_unit SET map_x = ?, map_y = ? WHERE id = ? AND course_id = ? AND (del_flag IS NULL OR del_flag = 0)", sql);
    }
    @Test public void contentEditNeverPassesStaleMapCoordinatesToEntityUpdate() {
        ITeachingCourseUnitService units = mock(ITeachingCourseUnitService.class);
        when(units.updateById(any(TeachingCourseUnit.class))).thenReturn(true);
        TeachingCourseUnitController controller = new TeachingCourseUnitController();
        ReflectionTestUtils.setField(controller, "teachingCourseUnitService", units);
        TeachingCourseUnit stale = new TeachingCourseUnit();
        stale.setId("a1"); stale.setMapX(1); stale.setMapY(2); stale.setUnitIntro("new content");
        assertTrue(controller.edit(stale).isSuccess());
        verify(units).updateById(argThat(unit -> unit.getMapX() == null && unit.getMapY() == null
                && "new content".equals(unit.getUnitIntro())));
    }
    private static class SnapshotTransactions extends AbstractPlatformTransactionManager {
        private final Map<String, List<Integer>> store;
        private Map<String, List<Integer>> snapshot;
        int commits, rollbacks;
        SnapshotTransactions(Map<String, List<Integer>> store) { this.store = store; }
        @Override protected Object doGetTransaction() { return new Object(); }
        @Override protected void doBegin(Object transaction, TransactionDefinition definition) { snapshot = new HashMap<>(store); }
        @Override protected void doCommit(DefaultTransactionStatus status) { commits++; }
        @Override protected void doRollback(DefaultTransactionStatus status) { store.clear(); store.putAll(snapshot); rollbacks++; }
    }
}
