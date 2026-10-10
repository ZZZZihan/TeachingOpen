package org.jeecg.duplicate;

import java.io.InputStream;
import java.io.StringWriter;
import java.util.*;
import freemarker.template.Template;
import freemarker.template.TemplateException;
import freemarker.template.TemplateExceptionHandler;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.BoundSql;
import org.apache.ibatis.session.Configuration;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.controller.DuplicateCheckController;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.DuplicateCheckMapper;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.mapper.SysUserRoleMapper;
import org.jeecg.modules.system.model.DuplicateCheckVo;
import org.jeecg.modules.system.service.DuplicateCheckService;
import org.junit.*;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

public class DuplicateCheckSecurityTest {
    private static final String[] MANAGEMENT = {"user_username", "user_phone", "user_email", "user_work_no",
            "role_code", "dict_code", "permission_perms", "position_code", "depart_role_code",
            "message_template_code", "fill_rule_code", "check_rule_code", "data_source_code"};
    private DuplicateCheckMapper checks;
    private SysUserMapper users;
    private SysUserRoleMapper roles;
    private DuplicateCheckService service;
    private MockMvc http;
    private Subject subject;
    private SysUser actor, target;

    @Before public void setup() {
        checks = mock(DuplicateCheckMapper.class); users = mock(SysUserMapper.class); roles = mock(SysUserRoleMapper.class);
        service = new DuplicateCheckService(checks, users, roles);
        http = MockMvcBuilders.standaloneSetup(new DuplicateCheckController(service)).build();
        actor = new SysUser().setId("operator-id").setDelFlag(0).setStatus(1).setPhone("13900000001");
        target = new SysUser().setId("target-id").setDelFlag(0).setStatus(1);
        LoginUser principal = new LoginUser(); principal.setId(actor.getId());
        subject = mock(Subject.class); when(subject.getPrincipal()).thenReturn(principal); ThreadContext.bind(subject);
        when(users.selectById(actor.getId())).thenReturn(actor);
        when(users.selectById(target.getId())).thenReturn(target);
        when(roles.getRoleByUserId(actor.getId())).thenReturn(Collections.singletonList("dev"));
        when(roles.getUserRoleLevel(actor.getId())).thenReturn(10);
        when(roles.getUserRoleLevel(target.getId())).thenReturn(1);
        when(checks.targetId(anyString(), anyString())).thenAnswer(call -> call.getArgument(1));
        when(checks.count(anyString(), anyString(), nullable(String.class))).thenReturn(0L);
    }
    @After public void cleanup() { ThreadContext.remove(); }

    private DuplicateCheckVo input(String purpose, String value, String id) {
        DuplicateCheckVo result = new DuplicateCheckVo(); result.setPurpose(purpose); result.setFieldVal(value); result.setDataId(id);
        return result;
    }
    private void response(String purpose, String value, String id, boolean available, int code) throws Exception {
        http.perform(get("/sys/duplicate/check").param("purpose", purpose).param("fieldVal", value)
                        .param("dataId", id == null ? "" : id))
                .andExpect(status().isOk()).andExpect(jsonPath("$.success").value(available))
                .andExpect(jsonPath("$.code").value(code)).andExpect(jsonPath("$.result").doesNotExist());
    }

    @Test public void everyManagementPurposePreservesCreateDuplicateAndAuthorizedEdit() throws Exception {
        for (String purpose : MANAGEMENT) {
            response(purpose, "candidate", null, true, 200);
            when(checks.count(eq(purpose), eq("existing"), isNull())).thenReturn(1L);
            response(purpose, "existing", null, false, 500);
            response(purpose, "existing", purpose.startsWith("user_") ? target.getId() : "object-id", true, 200);
        }
    }

    @Test public void arbitraryLegacyAndMixedParametersAreRejectedBeforeAnyDatabaseAccess() throws Exception {
        for (String name : Arrays.asList("tableName", "fieldName", "table", "field", "condition", "unexpected")) {
            for (String value : Arrays.asList("", "sys_user", "password AND SUBSTRING(password,1,1)='a' AND username")) {
                http.perform(get("/sys/duplicate/check").param("purpose", "user_username").param("fieldVal", "x").param(name, value))
                        .andExpect(jsonPath("$.success").value(false)).andExpect(jsonPath("$.code").value(400));
            }
        }
        http.perform(get("/sys/duplicate/check").param("tableName", "sys_user").param("fieldName", "password").param("fieldVal", "x"))
                .andExpect(jsonPath("$.code").value(400));
        http.perform(get("/sys/duplicate/check").param("purpose", "user_username", "profile_email").param("fieldVal", "x"))
                .andExpect(jsonPath("$.code").value(400));
        http.perform(get("/sys/duplicate/check").param("purpose", "user_username").param("fieldVal", "x", "y"))
                .andExpect(jsonPath("$.code").value(400));
        verifyZeroInteractions(checks, users, roles);
    }

    @Test public void malformedPurposesValuesAndIdsNeverReachDataQueries() throws Exception {
        for (String purpose : Arrays.asList("sys_user.password", "user_password", "user_salt", "USER_USERNAME", " user_username")) {
            response(purpose, "x", null, false, 400);
        }
        response("user_username", "", null, false, 400);
        response("user_username", String.join("", Collections.nCopies(256, "x")), null, false, 400);
        response("user_username", "x\n", null, false, 400);
        for (String id : Arrays.asList(" ", "x' OR 1=1", "x,y", String.join("", Collections.nCopies(65, "x")))) {
            response("user_username", "x", id, false, 400);
        }
        verifyZeroInteractions(checks, users, roles);
    }

    @Test public void studentsTeachersAndRevokedCachedManagersCannotProbeManagementData() throws Exception {
        when(subject.hasRole("dev")).thenReturn(true); when(subject.hasRole("admin")).thenReturn(true);
        for (String role : Arrays.asList("student", "teacher", "revoked")) {
            when(roles.getRoleByUserId(actor.getId())).thenReturn(Collections.singletonList(role));
            for (String purpose : MANAGEMENT) response(purpose, "x", null, false, 403);
        }
        verifyZeroInteractions(checks);
        verify(subject, never()).hasRole(anyString());
    }

    @Test public void sameSessionLosesAccessImmediatelyAfterDatabaseGrantRevocation() throws Exception {
        when(roles.getRoleByUserId(actor.getId())).thenReturn(Collections.singletonList("admin"));
        response("user_username", "before", null, true, 200);
        when(roles.getRoleByUserId(actor.getId())).thenReturn(Collections.singletonList("student"));
        response("user_username", "after", null, false, 403);
        verify(checks, times(1)).count(anyString(), anyString(), nullable(String.class));
    }

    @Test public void administratorCannotUseDeveloperOnlyRoleForm() throws Exception {
        when(roles.getRoleByUserId(actor.getId())).thenReturn(Collections.singletonList("admin"));
        response("dict_code", "x", null, true, 200);
        response("role_code", "x", null, false, 403);
        verify(checks, never()).count(eq("role_code"), anyString(), nullable(String.class));
    }

    @Test public void anonymousDeletedFrozenAndMissingActorsCannotQuery() throws Exception {
        when(subject.getPrincipal()).thenReturn(null);
        response("user_username", "x", null, false, 403);
        LoginUser principal = new LoginUser(); principal.setId(actor.getId()); when(subject.getPrincipal()).thenReturn(principal);
        actor.setStatus(2); response("user_username", "x", null, false, 403);
        actor.setStatus(1).setDelFlag(1); response("user_username", "x", null, false, 403);
        when(users.selectById(actor.getId())).thenReturn(null); response("user_username", "x", null, false, 403);
        verifyZeroInteractions(checks, roles);
    }

    @Test public void invalidMissingCaseAliasedDeletedAndHigherLevelUserExclusionsAreDenied() throws Exception {
        response("user_email", "x", "missing-id", false, 400);
        when(users.selectById("TARGET-ID")).thenReturn(target);
        response("user_email", "x", "TARGET-ID", false, 400);
        target.setDelFlag(1); response("user_email", "x", target.getId(), false, 400);
        target.setDelFlag(0); when(roles.getUserRoleLevel(target.getId())).thenReturn(11);
        response("user_email", "x", target.getId(), false, 403);
        verifyZeroInteractions(checks);
    }

    @Test public void everyNonUserPurposeResolvesItsOwnExactTargetBeforeCounting() throws Exception {
        for (String purpose : MANAGEMENT) {
            if (purpose.startsWith("user_")) continue;
            when(checks.targetId(purpose, "missing-id")).thenReturn(null);
            response(purpose, "x", "missing-id", false, 400);
            when(checks.targetId(purpose, "OBJECT-ID")).thenReturn("object-id");
            response(purpose, "x", "OBJECT-ID", false, 400);
            verify(checks, never()).count(eq(purpose), anyString(), nullable(String.class));
        }
    }

    @Test public void profilePurposesAllowOnlyOwnIdentityAndCurrentImmutablePhone() throws Exception {
        when(roles.getRoleByUserId(actor.getId())).thenReturn(Collections.singletonList("student"));
        response("profile_email", "candidate@example.invalid", actor.getId(), true, 200);
        response("profile_phone", actor.getPhone(), actor.getId(), true, 200);
        response("profile_email", "x", null, false, 403);
        response("profile_email", "x", target.getId(), false, 403);
        response("profile_phone", "13900000002", actor.getId(), false, 403);
        verify(checks, times(2)).count(anyString(), anyString(), nullable(String.class));
        verifyZeroInteractions(roles);
    }

    @Test public void missingCountCannotBeReportedAsAvailable() {
        when(checks.count(anyString(), anyString(), nullable(String.class))).thenReturn(null);
        try { service.available(input("user_username", "x", null)); fail("null query outcome must fail closed"); }
        catch (IllegalStateException expected) { assertEquals("重复校验未完成", expected.getMessage()); }
    }

    @Test public void realMybatisSqlBindsCandidateAndExclusionForEveryLiteralPurpose() throws Exception {
        String resource = "org/jeecg/modules/system/mapper/xml/DuplicateCheckMapper.xml";
        Configuration config = new Configuration();
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertNotNull(stream); new XMLMapperBuilder(stream, config, resource, config.getSqlFragments()).parse();
        }
        Map<String, String[]> expected = new LinkedHashMap<>();
        expected.put("user_username", new String[]{"sys_user", "username"});
        expected.put("user_phone", new String[]{"sys_user", "phone"}); expected.put("profile_phone", new String[]{"sys_user", "phone"});
        expected.put("user_email", new String[]{"sys_user", "email"}); expected.put("profile_email", new String[]{"sys_user", "email"});
        expected.put("user_work_no", new String[]{"sys_user", "work_no"}); expected.put("role_code", new String[]{"sys_role", "role_code"});
        expected.put("dict_code", new String[]{"sys_dict", "dict_code"}); expected.put("permission_perms", new String[]{"sys_permission", "perms"});
        expected.put("position_code", new String[]{"sys_position", "code"}); expected.put("depart_role_code", new String[]{"sys_depart_role", "role_code"});
        expected.put("message_template_code", new String[]{"sys_sms_template", "template_code"});
        expected.put("fill_rule_code", new String[]{"sys_fill_rule", "rule_code"}); expected.put("check_rule_code", new String[]{"sys_check_rule", "rule_code"});
        expected.put("data_source_code", new String[]{"sys_data_source", "code"});
        for (Map.Entry<String, String[]> entry : expected.entrySet()) {
            Map<String, Object> params = new HashMap<>(); params.put("purpose", entry.getKey());
            params.put("fieldVal", "x' OR SUBSTRING(password,1,1)='a' --"); params.put("dataId", "object-id");
            BoundSql bound = config.getMappedStatement(DuplicateCheckMapper.class.getName() + ".count").getBoundSql(params);
            assertEquals("SELECT COUNT(*) FROM " + entry.getValue()[0] + " WHERE " + entry.getValue()[1] + " = ? AND id <> ?",
                    bound.getSql().replaceAll("\\s+", " ").trim());
            assertEquals("fieldVal", bound.getParameterMappings().get(0).getProperty());
            assertEquals("dataId", bound.getParameterMappings().get(1).getProperty());
            params.put("dataId", null);
            assertEquals(1, config.getMappedStatement(DuplicateCheckMapper.class.getName() + ".count").getBoundSql(params).getParameterMappings().size());
        }
    }

    @Test public void realCodeGeneratorTemplateUsesNamedPurposesAndStopsUnknownUniqueChecks() throws Exception {
        freemarker.template.Configuration config = new freemarker.template.Configuration(freemarker.template.Configuration.VERSION_2_3_28);
        config.setClassLoaderForTemplateLoading(getClass().getClassLoader(), "jeecg/code-template-online/common");
        config.setDefaultEncoding("UTF-8"); config.setTemplateExceptionHandler(TemplateExceptionHandler.RETHROW_HANDLER);
        config.setLogTemplateExceptions(false);
        Template template = config.getTemplate("validatorRulesTemplate/core.ftl");
        String[][] configured = {
                {"sys_user", "username", "user_username"}, {"sys_user", "phone", "user_phone"},
                {"sys_user", "email", "user_email"}, {"sys_user", "work_no", "user_work_no"},
                {"sys_role", "role_code", "role_code"}, {"sys_dict", "dict_code", "dict_code"},
                {"sys_permission", "perms", "permission_perms"}, {"sys_position", "code", "position_code"},
                {"sys_depart_role", "role_code", "depart_role_code"}, {"sys_sms_template", "template_code", "message_template_code"},
                {"sys_fill_rule", "rule_code", "fill_rule_code"}, {"sys_check_rule", "rule_code", "check_rule_code"},
                {"sys_data_source", "code", "data_source_code"}
        };
        Map<String, Object> po = new HashMap<>(); po.put("isShow", "Y"); po.put("nullable", "N");
        po.put("fieldName", "testCode"); po.put("fieldValidType", "only"); po.put("filedComment", "合成编码");
        Map<String, Object> model = new HashMap<>(); model.put("po", po);
        for (String[] purpose : configured) {
            model.put("tableName", purpose[0]); po.put("fieldDbName", purpose[1]);
            StringWriter rendered = new StringWriter(); template.process(model, rendered);
            assertTrue(rendered.toString().contains("validateDuplicateValue('" + purpose[2] + "', value, this.model.id, callback)"));
            assertFalse(rendered.toString().contains("validateDuplicateValue('" + purpose[0] + "',"));
        }
        for (String[] unknown : new String[][]{{"sys_user", "password"}, {"sys_user", "salt"}, {"new_business", "unique_code"}}) {
            model.put("tableName", unknown[0]); po.put("fieldDbName", unknown[1]);
            try { template.process(model, new StringWriter()); fail("unconfigured unique validator must stop generation"); }
            catch (TemplateException expected) { assertTrue(expected.getMessage().contains("未配置此字段的唯一校验用途")); }
        }
    }
}
