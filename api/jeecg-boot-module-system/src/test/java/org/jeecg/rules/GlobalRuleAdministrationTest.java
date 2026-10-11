package org.jeecg.rules;

import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.Wrapper;
import org.apache.poi.hssf.usermodel.HSSFWorkbook;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.exception.*;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.FillRuleUtil;
import org.jeecg.common.util.SpringContextUtils;
import org.jeecg.modules.system.controller.*;
import org.jeecg.modules.system.entity.*;
import org.jeecg.modules.system.mapper.*;
import org.jeecg.modules.system.model.TreeSelectModel;
import org.jeecg.modules.system.service.*;
import org.jeecg.modules.system.service.impl.*;
import org.junit.*;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import java.io.ByteArrayOutputStream;
import java.util.*;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

public class GlobalRuleAdministrationTest {
    private SysUserMapper users;
    private SysUserRoleMapper roles;
    private SysFillRuleMapper fills;
    private SysCheckRuleMapper checks;
    private SysCategoryMapper categories;
    private SysFillRuleServiceImpl fillService;
    private SysCheckRuleServiceImpl checkService;
    private SysCategoryServiceImpl categoryService;
    private SysUser actor;
    private Subject subject;
    private MockMvc http;
    private GenericApplicationContext context;
    private static final String CHECK="[{\"digits\":\"*\",\"pattern\":\"^[A-Za-z]{1,12}$\",\"message\":\"Letters only\"}]";

    @Before public void setup() {
        users=mock(SysUserMapper.class); roles=mock(SysUserRoleMapper.class); fills=mock(SysFillRuleMapper.class);
        checks=mock(SysCheckRuleMapper.class); categories=mock(SysCategoryMapper.class);
        GlobalResourceAccessService access=new GlobalResourceAccessService(users,roles);
        actor=new SysUser().setId("actor").setUsername("manager").setStatus(1).setDelFlag(0);
        LoginUser login=new LoginUser();login.setId("actor");subject=mock(Subject.class);
        when(subject.getPrincipal()).thenReturn(login);when(subject.hasRole(anyString())).thenReturn(true);ThreadContext.bind(subject);
        when(users.selectById("actor")).thenReturn(actor);when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("admin"));
        fillService=new SysFillRuleServiceImpl();checkService=new SysCheckRuleServiceImpl();categoryService=new SysCategoryServiceImpl();
        ReflectionTestUtils.setField(fillService,"baseMapper",fills);ReflectionTestUtils.setField(checkService,"baseMapper",checks);ReflectionTestUtils.setField(categoryService,"baseMapper",categories);
        for (Object service : Arrays.asList(fillService,checkService,categoryService)) ReflectionTestUtils.setField(service,"access",access);
        when(fills.insert(any(SysFillRule.class))).thenReturn(1);when(checks.insert(any(SysCheckRule.class))).thenReturn(1);when(categories.insert(any(SysCategory.class))).thenReturn(1);
        when(fills.updateById(any(SysFillRule.class))).thenReturn(1);when(checks.updateById(any(SysCheckRule.class))).thenReturn(1);when(categories.updateById(any(SysCategory.class))).thenReturn(1);
        when(fills.selectById("existing")).thenReturn(fill().setId("existing"));when(checks.selectById("existing")).thenReturn(check().setId("existing"));when(categories.selectById("existing")).thenReturn(category());
        SysFillRuleController fillController=new SysFillRuleController();SysCheckRuleController checkController=new SysCheckRuleController();SysCategoryController categoryController=new SysCategoryController();
        ReflectionTestUtils.setField(fillController,"sysFillRuleService",fillService);ReflectionTestUtils.setField(checkController,"sysCheckRuleService",checkService);ReflectionTestUtils.setField(categoryController,"sysCategoryService",categoryService);
        ReflectionTestUtils.setField(fillController,"service",fillService);ReflectionTestUtils.setField(checkController,"service",checkService);
        for(Object controller:Arrays.asList(fillController,checkController,categoryController)) ReflectionTestUtils.setField(controller,"access",access);
        http=MockMvcBuilders.standaloneSetup(fillController,checkController,categoryController).setControllerAdvice(new JeecgBootExceptionHandler()).build();
        context=new GenericApplicationContext();context.getBeanFactory().registerSingleton("sysFillRuleServiceImpl",fillService);
        context.getBeanFactory().registerSingleton("sysCategoryMapper",categories);
        ISysDepartService departments=mock(ISysDepartService.class);when(departments.list(any(Wrapper.class))).thenReturn(Collections.emptyList());
        context.getBeanFactory().registerSingleton("sysDepartServiceImpl",departments);context.refresh();new SpringContextUtils().setApplicationContext(context);
    }
    @After public void cleanup() { ThreadContext.remove();context.close(); }
    private SysFillRule fill() { return new SysFillRule().setRuleName("Fixture").setRuleCode("fixture_fill").setRuleClass(FillRuleUtil.ORGANIZATION).setRuleParams("{}"); }
    private SysCheckRule check() { return new SysCheckRule().setRuleName("Fixture").setRuleCode("fixture_check").setRuleJson(CHECK); }
    private SysCategory category() { SysCategory result=new SysCategory();result.setId("existing");result.setName("Fixture");result.setPid("0");result.setCode("A99");return result; }
    private void student() { when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("student")); }
    private void deny(Runnable operation) { try { operation.run();fail("Unauthorized management accepted"); } catch(UnauthorizedException expected) { } }
    private void invalid(Runnable operation) { try { operation.run();fail("Invalid configuration accepted"); } catch(JeecgBootException expected) { } }
    @Test public void studentCannotSaveFillRule() { student();deny(() -> fillService.save(fill()));verifyZeroInteractions(fills); }
    @Test public void studentCannotSaveCheckRule() { student();deny(() -> checkService.save(check()));verifyZeroInteractions(checks); }
    @Test public void studentCannotSaveCategory() { student();deny(() -> categoryService.save(category()));verifyZeroInteractions(categories); }

    @Test public void teacherStudentAndRevokedCachedGrantsDenyAllMutationPaths() {
        for(List<String> grants:Arrays.asList(Arrays.asList("student"),Arrays.asList("teacher"),Collections.<String>emptyList())) {
            when(roles.getRoleByUserId("actor")).thenReturn(grants);
            for(GlobalResourceService service:Arrays.asList(fillService,checkService,categoryService)) {
                deny(() -> service.save(null));deny(() -> service.updateById(null));deny(() -> service.saveBatch(Arrays.asList((Object)null)));
                deny(() -> service.removeById("existing"));deny(() -> service.removeByIds(Arrays.asList("existing")));
                deny(() -> service.saveOrUpdate(null));deny(() -> service.update(null,null));deny(() -> service.removeByMap(Collections.emptyMap()));
            }
            deny(() -> categoryService.addSysCategory(category()));deny(() -> categoryService.updateSysCategory(category()));
        }
        verifyZeroInteractions(fills,checks,categories);verify(subject,never()).hasRole(anyString());
    }
    @Test public void allManagementHttpAliasesDenyBeforeLookupAndExcelParsing() throws Exception {
        for(String role:Arrays.asList("student","teacher")) {
            when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList(role));
            for(String type:Arrays.asList("fillRule","checkRule","category")) {
                String base="/sys/"+type;
                for(org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request:Arrays.asList(
                        get(base+(type.equals("category")?"/rootList":"/list")),get(base+"/queryById").param("id","existing"),get(base+"/exportXls"),
                        post(base+"/add").contentType("application/json").content("{}"),put(base+"/edit").contentType("application/json").content("{}"),
                        delete(base+"/delete").param("id","existing"),delete(base+"/deleteBatch").param("ids","existing,other"),post(base+"/importExcel"))) {
                    http.perform(request).andExpect(jsonPath("$.success").value(false)).andExpect(jsonPath("$.code").value(510));
                }
            }
            http.perform(get("/sys/fillRule/testFillRule").param("ruleCode","fixture_fill")).andExpect(jsonPath("$.code").value(510));
            http.perform(get("/sys/category/childList").param("pid","existing")).andExpect(jsonPath("$.code").value(510));
        }
        verifyZeroInteractions(fills,checks,categories);
    }
    @Test public void adminAndDevCrudWhitelistsAuditFieldsAndAllImports() throws Exception {
        for(String role:Arrays.asList("admin","dev")) {
            when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList(role));
            fillService.save(fill().setCreateBy("other"));checkService.save(check().setCreateBy("other"));categoryService.save(category());
            fillService.updateById(fill().setId("existing"));checkService.updateById(check().setId("existing"));categoryService.updateSysCategory(category());
            for(GlobalResourceService service:Arrays.asList(fillService,checkService,categoryService)) { service.removeById("existing");service.removeByIds(Arrays.asList("existing","other")); }
            http.perform(multipart("/sys/fillRule/importExcel").file(workbook(new String[]{"规则名称","规则Code","规则实现类","规则参数"}, new String[][]{{"Fixture","fixture_import",FillRuleUtil.ORGANIZATION,"{}"}}))).andExpect(jsonPath("$.success").value(true));
            http.perform(multipart("/sys/checkRule/importExcel").file(workbook(new String[]{"规则名称","规则Code","规则JSON"}, new String[][]{{"Fixture","fixture_import",CHECK}}))).andExpect(jsonPath("$.success").value(true));
            http.perform(multipart("/sys/category/importExcel").file(workbook(new String[]{"类型名称","类型编码","父级节点"}, new String[][]{{"Fixture","A991","0"}}))).andExpect(jsonPath("$.success").value(true));
        }
        org.mockito.ArgumentCaptor<SysFillRule> values=org.mockito.ArgumentCaptor.forClass(SysFillRule.class);verify(fills,times(4)).insert(values.capture());
        for(SysFillRule value:values.getAllValues()) assertEquals("manager",value.getCreateBy());
        verify(checks,times(4)).insert(any(SysCheckRule.class));verify(categories,times(4)).insert(any(SysCategory.class));
    }
    @Test public void unsupportedClassAndMixedInvalidImportCannotReachWrites() throws Exception {
        invalid(() -> fillService.save(fill().setRuleClass("java.lang.String")));
        invalid(() -> fillService.save(fill().setRuleCode("org_num_role").setRuleClass(FillRuleUtil.CATEGORY)));
        invalid(() -> fillService.saveBatch(Arrays.asList(fill(),fill().setRuleParams("{\"unexpected\":\"value\"}"))));
        invalid(() -> checkService.saveBatch(Arrays.asList(check(),check().setRuleJson("[]"))));
        SysCategory bad=category();bad.setName(null);invalid(() -> categoryService.saveBatch(Arrays.asList(category(),bad)));
        http.perform(multipart("/sys/fillRule/importExcel").file(workbook(new String[]{"规则名称","规则Code","规则实现类","规则参数"},
                new String[][]{{"Fixture","good",FillRuleUtil.ORGANIZATION,"{}"},{"Fixture","bad","java.lang.String","{}"}}))).andExpect(jsonPath("$.success").value(false));
        verifyZeroInteractions(fills,checks,categories);
    }
    @Test public void liveRevocationFrozenAndDeletedActorsCannotManage() {
        fillService.save(fill());clearInvocations(fills);
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.emptyList());deny(() -> fillService.save(fill()));
        when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("dev"));actor.setStatus(2);deny(() -> checkService.save(check()));
        actor.setStatus(1).setDelFlag(1);deny(() -> categoryService.addSysCategory(category()));verifyZeroInteractions(fills,checks,categories);
    }
    @Test public void ordinaryFormCheckAndBothBuiltInCodeGeneratorsStillWork() throws Exception {
        student();when(checks.selectOne(any(Wrapper.class))).thenReturn(check());
        http.perform(get("/sys/checkRule/checkByCode").param("ruleCode","fixture_check").param("value","Abc")).andExpect(jsonPath("$.success").value(true));
        http.perform(get("/sys/checkRule/checkByCode").param("ruleCode","fixture_check").param("value","123")).andExpect(jsonPath("$.success").value(false));
        when(fills.selectOne(any(Wrapper.class))).thenReturn(fill().setRuleCode("org_num_role"));
        http.perform(put("/sys/fillRule/executeRuleByCode/org_num_role").contentType("application/json").content("{}"))
                .andExpect(jsonPath("$.success").value(true)).andExpect(jsonPath("$.result[0]").value("A01"));
        when(fills.selectOne(any(Wrapper.class))).thenReturn(fill().setRuleCode("category_code_rule").setRuleClass(FillRuleUtil.CATEGORY));
        when(categories.selectList(any(Wrapper.class))).thenReturn(Collections.emptyList());
        assertEquals("A01",FillRuleUtil.executeRule("category_code_rule",new JSONObject()));
        when(fills.selectOne(any(Wrapper.class))).thenReturn(fill().setRuleClass("java.lang.String"));
        invalid(() -> FillRuleUtil.executeRule("fixture_fill",new JSONObject()));
        verify(fills,never()).insert(any(SysFillRule.class));verify(checks,never()).insert(any(SysCheckRule.class));verify(categories,never()).insert(any(SysCategory.class));
    }
    @Test public void existingFrontendUriEncodedValueIsDecodedExactlyOnce() throws Exception {
        student();
        JSONObject row=new JSONObject();row.put("digits","*");row.put("pattern","^A\\+B% C中文$");row.put("message","Exact original value required");
        when(checks.selectOne(any(Wrapper.class))).thenReturn(check().setRuleJson("["+row.toJSONString()+"]"));
        // validateCheckRule first uses encodeURIComponent; Axios then transports that string as a query parameter.
        http.perform(get("/sys/checkRule/checkByCode").param("ruleCode","fixture_check").param("value","A%2BB%25%20C%E4%B8%AD%E6%96%87"))
                .andExpect(jsonPath("$.success").value(true));
        http.perform(get("/sys/checkRule/checkByCode").param("ruleCode","fixture_check").param("value","%"))
                .andExpect(jsonPath("$.success").value(false)).andExpect(jsonPath("$.message").value("校验值编码不正确"));
        row.put("pattern","^%41$");
        when(checks.selectOne(any(Wrapper.class))).thenReturn(check().setRuleJson("["+row.toJSONString()+"]"));
        http.perform(get("/sys/checkRule/checkByCode").param("ruleCode","fixture_check").param("value","%2541"))
                .andExpect(jsonPath("$.success").value(true));
    }
    @Test public void encodedUnicodeLengthIsLimitedAfterDecodingBeforeRuleLookup() throws Exception {
        student();
        when(checks.selectOne(any(Wrapper.class))).thenReturn(check().setRuleJson("[{\"digits\":\"*\",\"pattern\":\"^中{256}$\",\"message\":\"Fixture\"}]"));
        String encoded=String.join("",Collections.nCopies(256,"%E4%B8%AD"));
        http.perform(get("/sys/checkRule/checkByCode").param("ruleCode","fixture_check").param("value",encoded))
                .andExpect(jsonPath("$.success").value(true));
        clearInvocations(checks);
        for(String value:Arrays.asList(encoded+"%E4%B8%AD",String.join("",Collections.nCopies(257,"a")),"%bad%")) {
            http.perform(get("/sys/checkRule/checkByCode").param("ruleCode","fixture_check").param("value",value))
                    .andExpect(jsonPath("$.success").value(false));
        }
        verifyZeroInteractions(checks);
    }
    @Test public void builtInGeneratorsKeepConfiguredParentFallbackAndFormOverride() {
        student();
        ISysDepartService departments=context.getBean(ISysDepartService.class);
        SysDepart orgParent=new SysDepart();orgParent.setId("org-parent");orgParent.setOrgCode("A01");orgParent.setOrgType("1");
        when(departments.getById("org-parent")).thenReturn(orgParent);
        when(fills.selectOne(any(Wrapper.class))).thenReturn(fill().setRuleCode("org_num_role").setRuleParams("{\"parentId\":\"org-parent\"}"));
        assertArrayEquals(new String[]{"A01A01","2"},(String[])FillRuleUtil.executeRule("org_num_role",null));
        assertArrayEquals(new String[]{"A01A01","2"},(String[])FillRuleUtil.executeRule("org_num_role",new JSONObject()));
        assertArrayEquals(new String[]{"A01","1"},(String[])FillRuleUtil.executeRule("org_num_role",JSONObject.parseObject("{\"parentId\":\"\"}")));
        assertArrayEquals(new String[]{"A01A01","2"},(String[])FillRuleUtil.executeRule("org_num_role",JSONObject.parseObject("{\"parentId\":\"org-parent\"}")));
        SysCategory catParent=category();catParent.setId("cat-parent");catParent.setCode("A02");
        when(categories.selectById("cat-parent")).thenReturn(catParent);when(categories.selectList(any(Wrapper.class))).thenReturn(Collections.emptyList());
        when(fills.selectOne(any(Wrapper.class))).thenReturn(fill().setRuleCode("category_code_rule").setRuleClass(FillRuleUtil.CATEGORY).setRuleParams("{\"pid\":\"cat-parent\"}"));
        assertEquals("A02A01",FillRuleUtil.executeRule("category_code_rule",null));
        assertEquals("A02A01",FillRuleUtil.executeRule("category_code_rule",new JSONObject()));
        assertEquals("A01",FillRuleUtil.executeRule("category_code_rule",JSONObject.parseObject("{\"pid\":\"0\"}")));
        assertEquals("A02A01",FillRuleUtil.executeRule("category_code_rule",JSONObject.parseObject("{\"pid\":\"cat-parent\"}")));
        verify(fills,never()).insert(any(SysFillRule.class));verify(categories,never()).insert(any(SysCategory.class));
    }
    @Test public void ordinaryCategorySelectorsKeepExistingReadContracts() throws Exception {
        student();
        TreeSelectModel node=new TreeSelectModel();node.setKey("existing");node.setTitle("Fixture");node.setValue("value");node.setCode("A99");node.setLeaf(true);
        when(categories.queryListByPid(anyString(),any())).thenReturn(Collections.singletonList(node));
        when(categories.selectList(any(Wrapper.class))).thenReturn(Collections.singletonList(category()));
        for(org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request:Arrays.asList(
                get("/sys/category/loadTreeData").param("pcode","0").param("condition","{\"name\":\"Fixture\"}"),
                get("/sys/category/loadTreeData").param("pid","existing"),
                get("/sys/category/loadTreeRoot").param("async","true").param("pcode",""),
                get("/sys/category/loadTreeChildren").param("pid","existing"))) {
            http.perform(request).andExpect(jsonPath("$.success").value(true)).andExpect(jsonPath("$.result[0].key").value("existing"))
                    .andExpect(jsonPath("$.result[0].leaf").value(true)).andExpect(jsonPath("$.result[0].title").value("Fixture"));
        }
        http.perform(get("/sys/category/loadDictItem").param("ids","existing").param("pcode","0"))
                .andExpect(jsonPath("$.success").value(true)).andExpect(jsonPath("$.result[0].name").value("Fixture"));
        for(String field:Arrays.asList("id","code")) {
            http.perform(get("/sys/category/loadOne").param("field",field).param("val",field.equals("id")?"existing":"A99"))
                    .andExpect(jsonPath("$.success").value(true)).andExpect(jsonPath("$.result.name").value("Fixture"));
        }
        http.perform(get("/sys/category/loadAllData").param("code","0"))
                .andExpect(jsonPath("$.success").value(true)).andExpect(jsonPath("$.result[0].text").value("Fixture"));
        verifyZeroInteractions(users,roles);verify(categories,never()).insert(any(SysCategory.class));
    }
    @Test public void normalSeedRulePatternsAndInputBoundsArePreserved() {
        String[] patterns={"^[a-z|A-Z]$","^[0-9|a-z|A-Z|_]{0,}$","^.{3,}$","^.{3,12}$","^\\d{3}$","^[^pP]*$","^@{4}$","^#=$","^O$","^.*。$"};
        for(String pattern:patterns) { JSONObject row=new JSONObject();row.put("digits","*");row.put("pattern",pattern);row.put("message","Fixture");CheckRuleValidator.rules("["+row.toJSONString()+"]"); }
        assertEquals("3", CheckRuleValidator.rules("[{\"digits\":3,\"pattern\":\"^[A-Za-z]{3}$\",\"message\":\"Fixture\"}]").getJSONObject(0).getString("digits"));
        invalid(() -> checkService.checkValue(check(),String.join("",Collections.nCopies(257,"a"))));
        invalid(() -> CheckRuleValidator.rules("[{\"digits\":\"-1\",\"pattern\":\"a\",\"message\":\"Fixture\"}]"));
    }
    private MockMultipartFile workbook(String[] headers,String[][] rows) throws Exception {
        HSSFWorkbook book=new HSSFWorkbook();Sheet sheet=book.createSheet("Fixture");sheet.createRow(0).createCell(0).setCellValue("Synthetic");sheet.createRow(1).createCell(0).setCellValue("Regression");
        Row head=sheet.createRow(2);for(int i=0;i<headers.length;i++)head.createCell(i).setCellValue(headers[i]);
        for(int i=0;i<rows.length;i++){Row row=sheet.createRow(i+3);for(int j=0;j<rows[i].length;j++)row.createCell(j).setCellValue(rows[i][j]);}
        try(ByteArrayOutputStream output=new ByteArrayOutputStream()){book.write(output);return new MockMultipartFile("file","fixture.xls","application/vnd.ms-excel",output.toByteArray());}
    }
}
