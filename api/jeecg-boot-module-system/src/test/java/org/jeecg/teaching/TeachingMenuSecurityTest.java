package org.jeecg.teaching;

import com.baomidou.mybatisplus.extension.service.IService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.mapper.SysUserRoleMapper;
import org.jeecg.modules.teaching.controller.TeachingMenuController;
import org.jeecg.modules.teaching.entity.TeachingMenu;
import org.jeecg.modules.teaching.mapper.TeachingMenuMapper;
import org.jeecg.modules.teaching.service.ITeachingMenuService;
import org.jeecg.modules.teaching.service.TeachingMenuAccessService;
import org.jeecg.modules.teaching.service.impl.TeachingMenuServiceImpl;
import org.jeecg.modules.teaching.util.TeachingMenuUrlPolicy;
import org.junit.*;
import org.mockito.ArgumentCaptor;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

public class TeachingMenuSecurityTest {
    private TeachingMenuMapper menus;
    private SysUserMapper users;
    private SysUserRoleMapper roles;
    private TeachingMenuServiceImpl service;
    private SysUser actor;
    private Subject subject;
    private MockMvc http;
    private TeachingMenu existing;
    @Before public void setup() {
        menus = mock(TeachingMenuMapper.class); users = mock(SysUserMapper.class); roles = mock(SysUserRoleMapper.class);
        actor = new SysUser().setId("operator").setUsername("fixture_operator").setStatus(1).setDelFlag(0);
        LoginUser principal = new LoginUser(); principal.setId(actor.getId());
        subject = mock(Subject.class); when(subject.getPrincipal()).thenReturn(principal);
        when(subject.hasRole(anyString())).thenReturn(true); ThreadContext.bind(subject);
        when(users.selectById("operator")).thenReturn(actor);
        when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList("admin"));
        service = new TeachingMenuServiceImpl(menus, new TeachingMenuAccessService(users, roles));
        http = MockMvcBuilders.standaloneSetup(new TeachingMenuController(service)).build();
        existing = menu().setId("stored").setCreateBy("original").setCreateTime(new Date(1));
        when(menus.selectById("stored")).thenReturn(existing);
        when(menus.selectList(any())).thenReturn(Collections.singletonList(existing));
        when(menus.insert(any())).thenReturn(1); when(menus.updateById(any())).thenReturn(1);
        when(menus.deleteBatchIds(anyCollection())).thenAnswer(i -> ((Collection<?>) i.getArgument(0)).size());
    }
    @After public void cleanup() { ThreadContext.remove(); }
    private TeachingMenu menu() { return new TeachingMenu().setName("Synthetic menu").setMenuType(0).setParentId("").setUrl("/courseList")
            .setSortNo(1D).setNeedLogin(0).setRoute(true).setDelFlag(0).setLeaf(true); }
    private List<Runnable> operations() { return Arrays.asList(() -> service.listManaged(null), () -> service.queryListByParentId(null),
            () -> service.addPermission(menu()), () -> service.editPermission(menu().setId("stored")),
            () -> service.deletePermission("stored"), () -> service.deletePermissions(Arrays.asList("stored", "missing"))); }
    private void deniedServices() {
        for (Runnable operation : operations()) { try { operation.run(); fail("management accepted"); } catch (UnauthorizedException expected) {} }
        verifyZeroInteractions(menus);
    }
    private List<MockHttpServletRequestBuilder> requests() { return Arrays.asList(get("/teaching/menu/list"), get("/teaching/menu/getSystemMenuList"),
            get("/teaching/menu/getSystemSubmenu").param("parentId", "stored"), get("/teaching/menu/getSystemSubmenuBatch").param("parentIds", "stored"),
            get("/teaching/menu/queryTreeList"), get("/teaching/menu/queryListAsync"), post("/teaching/menu/add").contentType("application/json").content("{}"),
            put("/teaching/menu/edit").contentType("application/json").content("{}"), post("/teaching/menu/edit").contentType("application/json").content("{}"),
            delete("/teaching/menu/delete").param("id", "stored"), delete("/teaching/menu/deleteBatch").param("ids", "stored,missing")); }
    private void invalid(Runnable operation) { try { operation.run(); fail("invalid menu accepted"); } catch (JeecgBootException expected) {} }

    @Test public void ordinaryAndStaleRolesCannotReachAnyManagementService() {
        for (String role : Arrays.asList("student", "teacher", "ADMIN", "dev ", "")) {
            when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList(role)); deniedServices();
        }
        when(roles.getRoleByUserId("operator")).thenReturn(null); deniedServices(); verify(subject, never()).hasRole(anyString());
    }
    @Test public void anonymousMissingFrozenDeletedAndMismatchedAccountsAreRejected() {
        when(subject.getPrincipal()).thenReturn(null); deniedServices();
        LoginUser principal = new LoginUser(); when(subject.getPrincipal()).thenReturn(principal); deniedServices();
        principal.setId("operator"); when(users.selectById("operator")).thenReturn(null); deniedServices();
        when(users.selectById("operator")).thenReturn(actor); actor.setStatus(2); deniedServices();
        actor.setStatus(1).setDelFlag(1); deniedServices(); actor.setDelFlag(0).setId("other"); deniedServices();
    }
    @Test public void everyControllerEntryReturns403BeforeMenuReadsOrWrites() throws Exception {
        for (String role : Arrays.asList("student", "teacher")) {
            when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList(role));
            for (MockHttpServletRequestBuilder request : requests()) http.perform(request).andExpect(status().isForbidden())
                    .andExpect(jsonPath("$.success").value(false)).andExpect(jsonPath("$.code").value(403));
        }
        verifyZeroInteractions(menus);
    }
    @Test public void samePrincipalLosesAuthorityImmediatelyAfterRevocation() throws Exception {
        http.perform(get("/teaching/menu/list")).andExpect(status().isOk()).andExpect(jsonPath("$.success").value(true));
        clearInvocations(menus); when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList("student"));
        deniedServices(); for (MockHttpServletRequestBuilder request : requests()) http.perform(request).andExpect(status().isForbidden());
        verifyZeroInteractions(menus);
    }
    @Test public void adminAndDevCanCreateServerOwnedRecords() {
        for (String role : Arrays.asList("admin", "dev")) {
            when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList(role));
            service.addPermission(menu().setId("forged").setCreateBy("forged").setUpdateBy("forged").setDelFlag(1).setLeaf(false));
        }
        ArgumentCaptor<TeachingMenu> saved = ArgumentCaptor.forClass(TeachingMenu.class); verify(menus, times(2)).insert(saved.capture());
        for (TeachingMenu row : saved.getAllValues()) {
            assertNotEquals("forged", row.getId()); assertNotNull(row.getId()); assertEquals("fixture_operator", row.getCreateBy());
            assertNull(row.getUpdateBy()); assertEquals(Integer.valueOf(0), row.getDelFlag()); assertTrue(row.isLeaf()); assertNotNull(row.getCreateTime());
        }
    }
    @Test public void everyLinkFlagCombinationRejectsActiveOrMalformedDestinations() {
        String[] rejected = {"javascript:void(0)", "JaVaScRiPt:void(0)", " java\nscript:void(0)", "data:text/html,synthetic", "vbscript:synthetic", "//example.invalid/", "/\\example.invalid/",
            "https:\\example.invalid/", "https://name:secret@example.invalid", "http://example.invalid", "/%2fexample.invalid", "/%5Cexample.invalid", "/%0aevil", "/%", "relative", "https://", "https://example.invalid:65536/", "https://exa mple.invalid"};
        for (String url : rejected) for (boolean route : new boolean[]{false, true}) for (boolean external : new boolean[]{false, true}) {
            assertNull(url, TeachingMenuUrlPolicy.safeUrl(url));
            invalid(() -> service.addPermission(menu().setUrl(url).setRoute(route).setInternalOrExternal(external)));
        }
        verifyZeroInteractions(menus);
    }
    @Test public void siteRoutesStaticEditorsHttpsAndGroupingLabelsRemainSupported() {
        for (String url : Arrays.asList("", "/", "/courseList", "/scratch3/index.html?scene=create", "/blockly/index.html?lang=zh#synthetic", "/课程?q=%E5%AD%A6", "https://example.invalid:443/a?q=x#fragment")) {
            assertEquals(url, TeachingMenuUrlPolicy.safeUrl(url)); service.addPermission(menu().setUrl(url).setInternalOrExternal(true));
        }
        ArgumentCaptor<TeachingMenu> saved = ArgumentCaptor.forClass(TeachingMenu.class); verify(menus, times(7)).insert(saved.capture());
        assertFalse(saved.getAllValues().get(0).isRoute()); assertFalse(saved.getAllValues().get(0).isInternalOrExternal());
        assertFalse(saved.getAllValues().get(6).isRoute()); assertTrue(saved.getAllValues().get(6).isInternalOrExternal());
    }
    @Test public void invalidWritableFieldsFailBeforeAnyWrite() {
        for (TeachingMenu value : Arrays.asList(menu().setName(" "), menu().setMenuType(2), menu().setNeedLogin(4), menu().setSortNo(Double.NaN),
                menu().setSortNo(Double.POSITIVE_INFINITY), menu().setSortNo(1000000D), menu().setIcon("<svg>"), menu().setUrl(String.join("", Collections.nCopies(256, "x")))))
            invalid(() -> service.addPermission(value));
        verifyZeroInteractions(menus);
    }
    @Test public void publicHistoricalUrlsAreFilteredWithoutMutatingStoredRecords() {
        TeachingMenu unsafe = menu().setId("unsafe").setUrl("javascript:void(0)").setRoute(false).setInternalOrExternal(true);
        TeachingMenu https = menu().setId("https").setUrl("https://example.invalid").setRoute(true);
        TeachingMenu hidden = menu().setHidden(true), deleted = menu().setDelFlag(1);
        when(menus.selectList(any())).thenReturn(Arrays.asList(unsafe, https, hidden, deleted)); when(subject.getPrincipal()).thenReturn(null);
        List<TeachingMenu> result = service.listPublic(); assertEquals(2, result.size());
        assertEquals("", result.get(0).getUrl()); assertFalse(result.get(0).isRoute()); assertFalse(result.get(0).isInternalOrExternal());
        assertEquals("javascript:void(0)", unsafe.getUrl()); assertTrue(unsafe.isInternalOrExternal());
        assertEquals("https://example.invalid", result.get(1).getUrl()); assertFalse(result.get(1).isRoute());
        verifyZeroInteractions(users, roles); verify(menus, never()).updateById(any());
    }
    @Test public void publicControllerServesSafeAnonymousTopAndChildLinks() throws Exception {
        TeachingMenu parent = menu().setId("parent").setLeaf(false).setUrl("javascript:void(0)");
        TeachingMenu child = menu().setId("child").setParentId("parent").setMenuType(1).setUrl("data:text/html,synthetic");
        when(menus.selectList(any())).thenReturn(Arrays.asList(parent, child)); when(subject.getPrincipal()).thenReturn(null);
        http.perform(get("/teaching/menu/getUserMenu")).andExpect(status().isOk()).andExpect(jsonPath("$.result[0].url").value(""))
                .andExpect(jsonPath("$.result[0].children[0].url").value(""));
        verifyZeroInteractions(users, roles);
    }
    @Test public void editsDoNotOverwriteCreationAuditOrAcceptClientLeafAndDeletedFlags() {
        when(menus.selectCount(any())).thenReturn(2);
        service.editPermission(menu().setId("stored").setCreateBy("forged").setCreateTime(new Date(7)).setUpdateBy("forged").setDelFlag(1).setLeaf(true)
                .setUrl("https://example.invalid").setRoute(true));
        ArgumentCaptor<TeachingMenu> saved = ArgumentCaptor.forClass(TeachingMenu.class); verify(menus).updateById(saved.capture());
        TeachingMenu value = saved.getValue(); assertEquals("original", value.getCreateBy()); assertEquals(new Date(1), value.getCreateTime());
        assertEquals("fixture_operator", value.getUpdateBy()); assertEquals(Integer.valueOf(0), value.getDelFlag()); assertFalse(value.isLeaf()); assertFalse(value.isRoute());
    }
    @Test public void cyclesAndMissingParentsCannotChangeTheTree() {
        invalid(() -> service.editPermission(menu().setId("stored").setMenuType(1).setParentId("stored")));
        when(menus.selectById("child")).thenReturn(menu().setId("child").setParentId("stored").setMenuType(1));
        invalid(() -> service.editPermission(menu().setId("stored").setMenuType(1).setParentId("child")));
        invalid(() -> service.addPermission(menu().setMenuType(1).setParentId("missing")));
        verify(menus, never()).insert(any()); verify(menus, never()).updateById(any()); verify(menus, never()).setMenuLeaf(anyString(), anyInt());
    }
    @Test public void batchValidatesEveryIdBeforeFirstDeleteAndPreservesRemainingParent() {
        invalid(() -> service.deletePermissions(Arrays.asList("stored", "missing")));
        verify(menus, never()).deleteBatchIds(anyCollection()); verify(menus, never()).setMenuLeaf(anyString(), anyInt());
        TeachingMenu parent = menu().setId("parent"); existing.setParentId("parent").setMenuType(1);
        TeachingMenu child = menu().setId("child").setParentId("stored").setMenuType(1);
        when(menus.selectList(any())).thenReturn(Arrays.asList(parent, existing, child));
        service.deletePermissions(Arrays.asList("stored", "stored"));
        verify(menus).deleteBatchIds(new LinkedHashSet<>(Arrays.asList("stored", "child"))); verify(menus).setMenuLeaf("parent", 1);
    }
    @Test public void bothEditMethodsRejectBadUrlsAndReportValidationWithoutSuccess() throws Exception {
        String body = new ObjectMapper().writeValueAsString(menu().setId("stored").setUrl("javascript:void(0)"));
        for (MockHttpServletRequestBuilder request : Arrays.asList(put("/teaching/menu/edit"), post("/teaching/menu/edit")))
            http.perform(request.contentType("application/json").content(body)).andExpect(status().isBadRequest()).andExpect(jsonPath("$.success").value(false));
        verify(menus, never()).updateById(any());
    }
    @Test public void writesHaveTransactionsAndNoInheritedGenericWriteEscape() throws Exception {
        assertFalse(IService.class.isAssignableFrom(ITeachingMenuService.class));
        for (String name : Arrays.asList("addPermission", "editPermission", "deletePermission", "deletePermissions")) {
            Class<?> parameter = name.equals("deletePermission") ? String.class : name.equals("deletePermissions") ? Collection.class : TeachingMenu.class;
            assertNotNull(TeachingMenuServiceImpl.class.getMethod(name, parameter).getAnnotation(Transactional.class));
        }
    }
}
