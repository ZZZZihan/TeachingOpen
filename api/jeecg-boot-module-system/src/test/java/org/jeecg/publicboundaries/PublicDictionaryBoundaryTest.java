package org.jeecg.publicboundaries;

import org.apache.shiro.subject.Subject;
import org.apache.shiro.authc.AuthenticationException;
import org.apache.shiro.authc.AuthenticationToken;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.config.ShiroConfig;
import org.jeecg.modules.shiro.authc.aop.MediaCookie;
import org.jeecg.modules.shiro.authc.aop.OptionalJwtFilter;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.system.vo.DictModel;
import org.jeecg.common.system.vo.DictQuery;
import org.jeecg.modules.system.controller.SysDictController;
import org.jeecg.modules.system.service.ISysDictService;
import org.jeecg.modules.system.service.NamedTableDictionaryService;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.Collections;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

public class PublicDictionaryBoundaryTest {
    private ISysDictService dictionaries;
    private SysDictController controller;
    private Subject subject;
    private MockHttpServletRequest request;
    private MockMvc http;

    @Before public void setup() {
        dictionaries = mock(ISysDictService.class);
        controller = new SysDictController();
        ReflectionTestUtils.setField(controller, "sysDictService", dictionaries);
        ReflectionTestUtils.setField(controller, "namedTableDictionaries", new NamedTableDictionaryService(dictionaries));
        subject = mock(Subject.class);
        ThreadContext.bind(subject);
        request = new MockHttpServletRequest();
        http = MockMvcBuilders.standaloneSetup(controller).build();
    }

    @After public void cleanup() { ThreadContext.remove(); }

    private void login(String role) {
        when(subject.getPrincipal()).thenReturn("synthetic-" + role);
        when(subject.hasRole(role)).thenReturn(true);
    }

    @Test public void anonymousScalarDictionaryStillUsesOnlyDictionaryCode() throws Exception {
        DictModel item = new DictModel("1", "学生");
        when(dictionaries.queryDictItemsByCode("sex")).thenReturn(Collections.singletonList(item));
        http.perform(get("/sys/dict/getDictItems/sex"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.result[0].text").value("学生"));
        verify(dictionaries).queryDictItemsByCode("sex");
        verifyNoMoreInteractions(dictionaries);
    }

    @Test public void configuredOptionalAuthenticationPreservesAnonymousScalarAndAuthenticatesManagerChoices() throws Exception {
        MediaCookie cookie = mock(MediaCookie.class);
        org.apache.shiro.spring.web.ShiroFilterFactoryBean factory = new ShiroConfig()
                .shiroFilter(mock(org.apache.shiro.mgt.SecurityManager.class), cookie);
        assertEquals("optionalJwt", factory.getFilterChainDefinitionMap().get("/sys/dict/getDictItems/**"));
        OptionalJwtFilter filter = (OptionalJwtFilter) factory.getFilters().get("optionalJwt");
        filter.processPathConfig("/sys/dict/getDictItems/**", null);
        MockHttpServletResponse response = new MockHttpServletResponse();
        request.addHeader("Origin", "http://127.0.0.1");
        request.addHeader("Access-Control-Request-Headers", "X-Access-Token");
        request.setRequestURI("/sys/dict/getDictItems/sex");
        request.setServletPath("/sys/dict/getDictItems/sex");
        final Result<?>[] result = new Result<?>[1];
        filter.doFilter(request, response, (req, res) -> result[0] = controller.getDictItems("sex", null, request));
        assertTrue(result[0].isSuccess());
        verify(subject, never()).login(any(AuthenticationToken.class));
        reset(dictionaries);

        request.setRequestURI("/sys/dict/getDictItems/course_options");
        request.setServletPath("/sys/dict/getDictItems/course_options");
        request.addHeader("X-Access-Token", "synthetic-manager-token");
        doAnswer(invocation -> { login("admin"); return null; }).when(subject).login(any(AuthenticationToken.class));
        filter.doFilter(request, response, (req, res) -> result[0] = controller.getDictItems("course_options", null, request));
        assertTrue(result[0].isSuccess());
        verify(subject).login(any(AuthenticationToken.class));
        verify(dictionaries).queryTableDictItemsByCode("teaching_course", "course_name", "id");

        reset(dictionaries);
        result[0] = null;
        doThrow(new AuthenticationException("synthetic expired token")).when(subject).login(any(AuthenticationToken.class));
        filter.doFilter(request, response, (req, res) -> result[0] = controller.getDictItems("course_options", null, request));
        assertNull(result[0]);
        assertEquals(401, response.getStatus());
        verifyZeroInteractions(dictionaries);
    }

    @Test public void anonymousAndStudentsCannotUseAnyRegisteredTablePurposeOrLegacyAlias() {
        for (String role : new String[]{null, "student", "teacher"}) {
            reset(subject);
            if (role != null) login(role);
            for (String code : new String[]{"course_options", "registration_roles", "category_tree",
                    "system_users", "sys_user,realname,id", "teaching_course,course_name,id"}) {
                assertFalse(controller.getDictItems(code, "forged-sign", request).isSuccess());
                assertFalse(controller.loadDict(code, "王", "forged-sign", request).isSuccess());
                assertFalse(controller.loadDictItem(code, "user-id", "forged-sign", request).isSuccess());
            }
            assertFalse(controller.loadTreeData("0", "category_tree", null, null, null, null,
                    null, null, "forged-sign", request).isSuccess());
            assertFalse(controller.queryTableData(new DictQuery(), 1, 10, "forged-sign", request).isSuccess());
        }
        verifyZeroInteractions(dictionaries);
    }

    @Test public void administratorCannotSelectSensitiveOrArbitrarySqlIdentifiersThroughAnyAlias() throws Exception {
        login("admin");
        for (String code : new String[]{"sys_user,password,id", "sys_user,salt,id", "sys_user,phone,id",
                "sys_user,realname,id,username!='admin'", "sys_user,realname,id,",
                "sys_user%2Cpassword%2Cid", "sys_user where 1=1,realname,id", "other_table,name,id"}) {
            assertFalse(controller.getDictItems(code, null, request).isSuccess());
            assertFalse(controller.loadDict(code, "x' OR 1=1", null, request).isSuccess());
            assertFalse(controller.loadDictItem(code, "id", null, request).isSuccess());
        }
        http.perform(get("/sys/dict/getDictItems/{code}", "sys_user,password,id"))
                .andExpect(jsonPath("$.success").value(false));
        http.perform(get("/sys/dict/loadDict/sys_user,password,id").param("keyword", "x"))
                .andExpect(jsonPath("$.success").value(false));
        http.perform(get("/sys/dict/loadDictItem/sys_user,password,id").param("key", "id"))
                .andExpect(jsonPath("$.success").value(false));
        http.perform(get("/sys/dict/queryTableData").param("table", "sys_user").param("text", "password")
                .param("code", "id").param("keyword", "' OR 1=1"))
                .andExpect(jsonPath("$.success").value(false));
        verifyZeroInteractions(dictionaries);
    }

    @Test public void administratorAndDeveloperKeepCourseChoicesAndExactLegacyCompatibility() {
        for (String role : new String[]{"admin", "dev"}) {
            reset(subject); login(role);
            assertTrue(controller.getDictItems("course_options", null, request).isSuccess());
            assertTrue(controller.getDictItems("teaching_course,course_name,id", null, request).isSuccess());
        }
        verify(dictionaries, times(4)).queryTableDictItemsByCode("teaching_course", "course_name", "id");
        verifyNoMoreInteractions(dictionaries);
    }

    @Test public void registrationRolesRemainAdministratorOnly() {
        login("dev");
        assertFalse(controller.getDictItems("registration_roles", null, request).isSuccess());
        assertFalse(controller.loadDict("sys_role,role_name,id", "角色", null, request).isSuccess());
        verifyZeroInteractions(dictionaries);
        login("admin");
        assertTrue(controller.getDictItems("registration_roles", null, request).isSuccess());
        verify(dictionaries).queryTableDictItemsByCode("sys_role", "role_name", "id");
    }

    @Test public void searchAndSelectedLabelUseFixedColumnsAndBoundUserValues() {
        login("admin");
        String keyword = "王' OR 1=1";
        String key = "id' OR 1=1";
        when(dictionaries.queryTableDictByKeys(eq("sys_depart"), eq("depart_name"), eq("id"), any(String[].class)))
                .thenReturn(Collections.singletonList("班级"));
        assertTrue(controller.loadDict("system_departments", keyword, null, request).isSuccess());
        Result<?> labels = controller.loadDictItem("system_departments", key, null, request);
        assertEquals(Collections.singletonList("班级"), labels.getResult());
        verify(dictionaries).queryTableDictItems("sys_depart", "depart_name", "id", keyword);
        verify(dictionaries).queryTableDictByKeys("sys_depart", "depart_name", "id", new String[]{key});
        verifyNoMoreInteractions(dictionaries);
    }

    @Test public void categoryAndMenuTreesHaveFixedParentFieldsAndRejectAllCustomFieldsAndConditions() throws Exception {
        login("admin");
        assertTrue(controller.loadTreeData("0", "category_tree", null, null, null, null,
                null, null, null, request).isSuccess());
        assertTrue(controller.loadTreeData("", "system_permissions", null, null, null, null,
                null, null, null, request).isSuccess());
        assertTrue(controller.loadTreeData("0", null, "pid", "sys_category", "name", "id",
                "", "", null, request).isSuccess());
        verify(dictionaries, times(2)).queryTreeList(Collections.emptyMap(), "sys_category", "name", "id", "pid", "0", "");
        verify(dictionaries).queryTreeList(Collections.emptyMap(), "sys_permission", "name", "id", "parent_id", "", "");
        clearInvocations(dictionaries);
        for (String[] fields : new String[][]{{"password", null, null}, {null, "salt", null}, {null, null, "{\"password\":\"x\"}"}}) {
            assertFalse(controller.loadTreeData("0", "category_tree", fields[0], null, null, null,
                    fields[1], fields[2], null, request).isSuccess());
        }
        assertFalse(controller.loadTreeData("0", "category_tree", null, "sys_user", "password", "id",
                null, null, null, request).isSuccess());
        http.perform(get("/sys/dict/loadTreeData").param("pid", "0").param("tableName", "sys_user")
                .param("text", "password").param("code", "id").param("pidField", "id"))
                .andExpect(jsonPath("$.success").value(false));
        verifyZeroInteractions(dictionaries);
    }

    @Test public void malformedAndExcessiveInputsAreRejectedBeforeQuery() {
        login("admin");
        assertFalse(controller.getDictItems("sex%00", null, request).isSuccess());
        assertFalse(controller.loadDict("system_departments", String.join("", Collections.nCopies(101, "x")), null, request).isSuccess());
        assertFalse(controller.loadDictItem("system_departments", "a,,b", null, request).isSuccess());
        assertFalse(controller.loadDictItem("system_departments", String.join(",", Collections.nCopies(101, "a")), null, request).isSuccess());
        verifyZeroInteractions(dictionaries);
    }
}
