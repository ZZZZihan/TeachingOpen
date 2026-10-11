package org.jeecg.authorization;

import java.util.*;
import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.constant.CacheConstant;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.controller.SysDictController;
import org.jeecg.modules.system.controller.SysDictItemController;
import org.jeecg.modules.system.entity.*;
import org.jeecg.modules.system.mapper.*;
import org.jeecg.modules.system.service.*;
import org.jeecg.modules.system.service.impl.SysDictServiceImpl;
import org.junit.*;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.*;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

public class DictionaryAdministrationTest {
    @Configuration @EnableCaching
    public static class Config {
        @Bean public SysUserMapper users() { return mock(SysUserMapper.class); }
        @Bean public SysUserRoleMapper roles() { return mock(SysUserRoleMapper.class); }
        @Bean public ISysDictService dictionaries() { return mock(ISysDictService.class); }
        @Bean public ISysDictItemService items() { return mock(ISysDictItemService.class); }
        @Bean public RedisTemplate<String, Object> redis() { return mock(RedisTemplate.class); }
        @Bean public CacheManager cacheManager() { return new ConcurrentMapCacheManager(CacheConstant.SYS_DICT_CACHE); }
        @Bean public DictionaryAdministrationService administration() {
            return new DictionaryAdministrationService(users(), roles(), dictionaries(), items(), redis());
        }
    }
    private AnnotationConfigApplicationContext context;
    private DictionaryAdministrationService service;
    private SysUserMapper users;
    private SysUserRoleMapper roles;
    private ISysDictService dictionaries;
    private ISysDictItemService items;
    private RedisTemplate<String, Object> redis;
    private org.springframework.cache.Cache cache;
    private SysUser actor;
    private Subject subject;
    private MockMvc http;

    @Before public void setup() {
        context = new AnnotationConfigApplicationContext(Config.class);
        service = context.getBean(DictionaryAdministrationService.class);
        users = context.getBean(SysUserMapper.class); roles = context.getBean(SysUserRoleMapper.class);
        dictionaries = context.getBean(ISysDictService.class); items = context.getBean(ISysDictItemService.class);
        redis = context.getBean(RedisTemplate.class);
        cache = context.getBean(CacheManager.class).getCache(CacheConstant.SYS_DICT_CACHE);
        actor = new SysUser().setId("actor").setDelFlag(0).setStatus(1);
        LoginUser principal = new LoginUser(); principal.setId("actor");
        subject = mock(Subject.class); when(subject.getPrincipal()).thenReturn(principal); ThreadContext.bind(subject);
        when(users.selectById("actor")).thenReturn(actor);
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("admin"));
        when(dictionaries.save(any(SysDict.class))).thenReturn(true);
        when(dictionaries.updateById(any(SysDict.class))).thenReturn(true);
        when(dictionaries.removeById(anyString())).thenReturn(true);
        when(dictionaries.removeByIds(anyCollection())).thenReturn(true);
        when(dictionaries.saveMain(any(SysDict.class), anyList())).thenReturn(1);
        when(items.save(any(SysDictItem.class))).thenReturn(true);
        when(items.updateById(any(SysDictItem.class))).thenReturn(true);
        when(items.removeById(anyString())).thenReturn(true);
        when(items.removeByIds(anyCollection())).thenReturn(true);
        SysDictController dictionary = new SysDictController();
        ReflectionTestUtils.setField(dictionary, "dictionaryAdministration", service);
        ReflectionTestUtils.setField(dictionary, "sysDictService", dictionaries);
        ReflectionTestUtils.setField(dictionary, "sysDictItemService", items);
        SysDictItemController item = new SysDictItemController();
        ReflectionTestUtils.setField(item, "dictionaryAdministration", service);
        ReflectionTestUtils.setField(item, "sysDictItemService", items);
        http = MockMvcBuilders.standaloneSetup(dictionary, item).build();
        // RedisTemplate receives BeanFactory/initialization callbacks at context startup.
        clearInvocations(redis);
    }
    @After public void cleanup() { ThreadContext.remove(); context.close(); }

    private List<Runnable> writes() {
        SysDict dict = new SysDict(); dict.setId("dict");
        SysDictItem item = new SysDictItem(); item.setId("item");
        return Arrays.asList(() -> service.addDictionary(dict), () -> service.editDictionary(dict),
                () -> service.deleteDictionary("dict"), () -> service.deleteDictionaries(Arrays.asList("dict")),
                () -> service.importDictionary(dict, Arrays.asList(item)), () -> service.deleteDictionaryPermanently("dict"),
                () -> service.restoreDictionary("dict"), () -> service.addItem(item), () -> service.editItem(item),
                () -> service.deleteItem("item"), () -> service.deleteItems(Arrays.asList("item")), () -> service.refreshCache());
    }
    private void assertAllDenied() {
        cache.put("sentinel", "retained");
        for (Runnable write : writes()) {
            try { write.run(); fail("Management operation accepted"); } catch (UnauthorizedException expected) { }
            assertEquals("retained", cache.get("sentinel", String.class));
        }
        verifyZeroInteractions(dictionaries, items, redis);
    }

    @Test public void studentTeacherAndRevokedCachedRolesCannotWriteOrEvict() {
        when(subject.hasRole(anyString())).thenReturn(true);
        for (List<String> grants : Arrays.asList(Collections.singletonList("student"), Collections.singletonList("teacher"),
                Collections.<String>emptyList(), Arrays.asList("ADMIN", "dev "))) {
            when(roles.getRoleByUserId("actor")).thenReturn(grants); assertAllDenied();
        }
        when(roles.getRoleByUserId("actor")).thenReturn(null); assertAllDenied();
        verify(subject, never()).hasRole(anyString());
    }

    @Test public void absentFrozenDeletedOrMismatchedActorsCannotWrite() {
        when(subject.getPrincipal()).thenReturn(null); assertAllDenied();
        LoginUser principal = new LoginUser(); when(subject.getPrincipal()).thenReturn(principal); assertAllDenied();
        principal.setId("actor"); when(users.selectById("actor")).thenReturn(null); assertAllDenied();
        when(users.selectById("actor")).thenReturn(actor); actor.setStatus(2); assertAllDenied();
        actor.setStatus(1).setDelFlag(1); assertAllDenied();
        actor.setDelFlag(0).setId("other"); assertAllDenied();
    }

    @Test public void bothManagerRolesRetainEveryServiceWorkflowAndEviction() {
        for (String role : Arrays.asList("admin", "dev")) {
            when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList(role));
            List<Runnable> operations = writes();
            for (int i = 0; i < operations.size() - 1; i++) {
                cache.put("sentinel", "stale"); operations.get(i).run(); assertNull(cache.get("sentinel"));
            }
            service.refreshCache();
        }
        verify(dictionaries, times(2)).save(any(SysDict.class));
        verify(dictionaries, times(2)).saveMain(any(SysDict.class), anyList());
        verify(dictionaries, times(2)).deleteOneDictPhysically("dict");
        verify(dictionaries, times(2)).updateDictDelFlag(0, "dict");
        verify(items, times(2)).save(any(SysDictItem.class));
        verify(redis, times(8)).keys(anyString());
    }

    @Test public void samePrincipalLosesAccessWhenDatabaseGrantIsRevoked() {
        service.addDictionary(new SysDict());
        clearInvocations(dictionaries);
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("student"));
        assertAllDenied();
    }

    @Test public void everyControllerEntryDeniesBeforeReadsParsingOrWrites() throws Exception {
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("student"));
        List<MockHttpServletRequestBuilder> requests = Arrays.asList(
                post("/sys/dict/add").contentType("application/json").content("{\"dictCode\":\"candidate\"}"),
                put("/sys/dict/edit").contentType("application/json").content("{\"id\":\"dict\"}"),
                delete("/sys/dict/delete").param("id", "dict"), delete("/sys/dict/deleteBatch").param("ids", "dict,other"),
                post("/sys/dict/importExcel"), delete("/sys/dict/deletePhysic/dict"), put("/sys/dict/back/dict"),
                get("/sys/dict/refleshCache"), post("/sys/dictItem/add").contentType("application/json").content("{}"),
                put("/sys/dictItem/edit").contentType("application/json").content("{\"id\":\"item\"}"),
                delete("/sys/dictItem/delete").param("id", "item"), delete("/sys/dictItem/deleteBatch").param("ids", "item,other"));
        cache.put("sentinel", "retained");
        for (MockHttpServletRequestBuilder request : requests) {
            http.perform(request).andExpect(status().isOk()).andExpect(jsonPath("$.success").value(false))
                    .andExpect(jsonPath("$.code").value(403));
            assertEquals("retained", cache.get("sentinel", String.class));
        }
        verifyZeroInteractions(dictionaries, items, redis);
    }

    @Test public void controllerStillAllowsManagerAddsAndItemAdds() throws Exception {
        http.perform(post("/sys/dict/add").contentType("application/json").content("{\"dictCode\":\"candidate\"}"))
                .andExpect(jsonPath("$.success").value(true));
        http.perform(post("/sys/dictItem/add").contentType("application/json").content("{\"dictId\":\"dict\",\"itemValue\":\"one\"}"))
                .andExpect(jsonPath("$.success").value(true));
        verify(dictionaries).save(any(SysDict.class)); verify(items).save(any(SysDictItem.class));
    }

    @Test public void childImportFailureEscapesForTransactionRollback() {
        SysDictServiceImpl imported = new SysDictServiceImpl();
        SysDictMapper parent = mock(SysDictMapper.class); SysDictItemMapper children = mock(SysDictItemMapper.class);
        ReflectionTestUtils.setField(imported, "sysDictMapper", parent);
        ReflectionTestUtils.setField(imported, "sysDictItemMapper", children);
        when(parent.insert(any(SysDict.class))).thenReturn(1);
        when(children.insert(any(SysDictItem.class))).thenThrow(new IllegalStateException("synthetic failure"));
        try { imported.saveMain(new SysDict(), Arrays.asList(new SysDictItem())); fail("Import failure swallowed"); }
        catch (IllegalStateException expected) { assertEquals("synthetic failure", expected.getMessage()); }
    }
}
