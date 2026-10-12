package org.jeecg.queryboundary;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.BoundSql;
import org.apache.ibatis.mapping.ParameterMapping;
import org.apache.ibatis.reflection.MetaObject;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.query.QueryGenerator;
import org.jeecg.modules.system.entity.*;
import org.jeecg.modules.system.model.SysUserModel;
import org.jeecg.modules.system.service.UserQueryAccessService;
import org.jeecg.modules.system.service.UserQueryFilters;
import org.jeecg.modules.system.mapper.*;
import org.jeecg.modules.system.service.ISysDepartService;
import org.jeecg.common.system.vo.LoginUser;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.apache.shiro.authz.UnauthorizedException;
import org.junit.*;
import java.io.InputStream;
import java.util.*;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

public class QuerySqlBoundaryTest {
    private MybatisConfiguration configuration;
    @Before public void setup() throws Exception {
        org.springframework.web.context.request.RequestContextHolder.setRequestAttributes(new org.springframework.web.context.request.ServletRequestAttributes(new org.springframework.mock.web.MockHttpServletRequest()));
        configuration = new MybatisConfiguration();
        String resource = "org/jeecg/modules/system/mapper/xml/SysUserMapper.xml";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertNotNull(stream);
            new XMLMapperBuilder(stream, configuration, resource, configuration.getSqlFragments()).parse();
        }
    }
    @After public void cleanup() { ThreadContext.unbindSubject(); org.springframework.web.context.request.RequestContextHolder.resetRequestAttributes(); }
    private Map<String,String[]> params(String key, String value) {
        Map<String,String[]> values=new HashMap<>(); values.put(key,new String[]{value}); return values;
    }
    private BoundSql sql(String id, Map<String,Object> parameters) {
        return configuration.getMappedStatement("org.jeecg.modules.system.mapper.SysUserMapper."+id).getBoundSql(parameters);
    }
    private List<Object> values(BoundSql sql, Map<String,Object> parameters) {
        List<Object> result=new ArrayList<>(); MetaObject meta=configuration.newMetaObject(parameters);
        for (ParameterMapping mapping:sql.getParameterMappings()) result.add(sql.hasAdditionalParameter(mapping.getProperty())
                ? sql.getAdditionalParameter(mapping.getProperty()) : meta.getValue(mapping.getProperty()));
        return result;
    }
    @Test public void orgPrefixIsBoundInBothRecordsAndCount() {
        String untrusted="A99' OR 1=1 --";
        Map<String,Object> parameters=new HashMap<>(); parameters.put("orgCode",untrusted); parameters.put("userParams",new SysUser());
        for(String statement:Arrays.asList("getUserByOrgCode","getUserByOrgCodeTotal")) {
            BoundSql sql=sql(statement,parameters); assertFalse(sql.getSql().contains(untrusted));
            assertTrue(sql.getSql().contains("LIKE CONCAT(?, '%')")); assertEquals(Arrays.asList(untrusted),values(sql,parameters));
        }
    }
    @Test public void roleAndDepartmentFiltersUseBoundExistsInRealMapper() {
        String role="x') OR 1=1 --", department="a'", allowed="teacher-class";
        QueryWrapper<SysUser> query=new QueryWrapper<>();
        UserQueryFilters.roles(query,Arrays.asList(role)); UserQueryFilters.departments(query,Arrays.asList(department));
        UserQueryFilters.departments(query,Arrays.asList(allowed)); query.orderByAsc("sys_user.id");
        Map<String,Object> parameters=new HashMap<>(); parameters.put("ew",query);
        BoundSql sql=sql("getUserList",parameters);
        assertFalse(sql.getSql().contains(role)); assertFalse(sql.getSql().contains(department));
        assertTrue(sql.getSql().contains("FROM sys_user_role user_relation"));
        assertTrue(sql.getSql().contains("FROM sys_user_depart user_relation"));
        assertEquals(Arrays.asList(role,department,allowed),values(sql,parameters));
    }
    @Test public void advancedValuesStayParametersAndLegalPropertyAliasesWork() {
        Map<String,String[]> params=params("superQueryParams","[{\"field\":\"realname\",\"rule\":\"eq\",\"val\":\"x' OR 1=1 --\"}]");
        params.put("column",new String[]{"createTime"}); params.put("order",new String[]{"descend"});
        QueryWrapper<SysUser> query=QueryGenerator.initQueryWrapper(new SysUser(),params);
        Map<String,Object> parameters=new HashMap<>(); parameters.put("ew",query);
        BoundSql sql=sql("getUserList",parameters);
        assertTrue(sql.getSql().contains("realname = ?")); assertTrue(sql.getSql().contains("ORDER BY create_time DESC"));
        assertEquals(Collections.singletonList("x' OR 1=1 --"),values(sql,parameters));
    }
    @Test public void unknownSqlExpressionAndTransientFieldsFailBeforeQuery() {
        for(String field:Arrays.asList("realname) OR 1=1 --","unknown","orgCodeTxt","roleTxt","sys_user.id","(select 1)","password, id","password","salt")) {
            try { QueryGenerator.initQueryWrapper(new SysUserModel(),params("column",field)); fail(field); }
            catch(JeecgBootException expected) { assertEquals("不支持的查询字段",expected.getMessage()); }
            try { QueryGenerator.initQueryWrapper(new SysUser(),params("superQueryParams","[{\"field\":\""+field+"\",\"rule\":\"eq\",\"val\":\"v\"}]")); fail(field); }
            catch(JeecgBootException expected) { assertEquals("不支持的查询字段",expected.getMessage()); }
        }
    }
    @Test public void malformedOrUnsupportedRuleDoesNotSilentlyBroadenQuery() {
        for(String input:Arrays.asList("not-json","[null]","[{\"field\":\"id\",\"rule\":\"ext\",\"val\":\"1=1\"}]")) {
            try { QueryGenerator.initQueryWrapper(new SysUser(),params("superQueryParams",input)); fail(input); }
            catch(JeecgBootException expected) { }
        }
    }
    @Test public void categoryColumnsAreResolvedAgainstItsOwnEntity() {
        assertEquals("has_child", QueryGenerator.requireColumn(SysCategory.class,"hasChild"));
        for(String field:Arrays.asList("password","id or 1=1","name desc")) {
            try { QueryGenerator.requireColumn(SysCategory.class,field); fail(field); }
            catch(JeecgBootException expected) { }
        }
    }
    @Test public void organizationRequiresLiveManagedObjectBeforeSearch() {
        SysUserMapper users=mock(SysUserMapper.class); SysUserRoleMapper roles=mock(SysUserRoleMapper.class);
        SysDepartMapper departments=mock(SysDepartMapper.class); ISysDepartService departmentService=mock(ISysDepartService.class);
        UserQueryAccessService access=new UserQueryAccessService(users,roles,departments,departmentService);
        LoginUser identity=new LoginUser(); identity.setId("teacher"); identity.setDepartIds("stale-class");
        Subject subject=mock(Subject.class); when(subject.getPrincipal()).thenReturn(identity); ThreadContext.bind(subject);
        SysUser live=new SysUser().setId("teacher").setStatus(1).setDelFlag(0).setDepartIds("class-a");
        when(users.selectById("teacher")).thenReturn(live); when(roles.getRoleByUserId("teacher")).thenReturn(Arrays.asList("teacher"));
        when(departmentService.getMySubDepIdsByDepId("class-a")).thenReturn(Arrays.asList("class-a"));
        SysDepart department=new SysDepart(); department.setId("class-a"); department.setOrgCode("A01"); department.setDelFlag("0");
        when(departments.selectOne(any())).thenReturn(department);
        assertEquals("A01",access.requireOrganization("A01"));
        for(String invalid:Arrays.asList("", "A01' OR 1=1", "A01%", "A", "A02")) {
            try { access.requireOrganization(invalid); fail(invalid); } catch(UnauthorizedException expected) { }
        }
        live.setDepartIds("class-b"); when(departmentService.getMySubDepIdsByDepId("class-b")).thenReturn(Arrays.asList("class-b"));
        try { access.requireOrganization("A01"); fail("stale scope"); } catch(UnauthorizedException expected) { }
        verify(departmentService,never()).getMySubDepIdsByDepId("stale-class");
        when(roles.getRoleByUserId("teacher")).thenReturn(Arrays.asList("student"));
        try { access.requireOrganization("A01"); fail("student"); } catch(UnauthorizedException expected) { }
    }
}
