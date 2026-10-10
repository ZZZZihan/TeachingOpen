package org.jeecg.pagination;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.config.MybatisPlusConfig;
import org.jeecg.config.PaginationRequestInterceptor;
import org.jeecg.modules.system.controller.SysUserController;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.model.SysUserModel;
import org.jeecg.modules.system.service.ISysUserService;
import org.jeecgframework.poi.excel.def.NormalExcelConstants;
import org.junit.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.servlet.ModelAndView;
import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

public class PaginationBoundaryTest {
    @RestController public static class ListController {
        final AtomicInteger calls = new AtomicInteger();
        @GetMapping("/list") public String list() { calls.incrementAndGet(); return "ok"; }
    }

    @Test public void invalidValuesNeverReachControllerOrDatabase() throws Exception {
        ListController controller = new ListController();
        MockMvc mvc = MockMvcBuilders.standaloneSetup(controller).addInterceptors(new PaginationRequestInterceptor()).build();
        for (String size : Arrays.asList("-1", "0", "101", "99999999999999999999999", "1.5", "", " 10", "+10", "abc"))
            mvc.perform(get("/list").param("pageSize", size)).andExpect(status().isBadRequest());
        for (String page : Arrays.asList("-1", "0", "2147483648", "1.5", "", "abc"))
            mvc.perform(get("/list").param("pageNo", page)).andExpect(status().isBadRequest());
        mvc.perform(get("/list").param("pageSize", "10", "-1")).andExpect(status().isBadRequest());
        assertEquals(0, controller.calls.get());
    }

    @Test public void defaultsAndBoundaryPagesAreAccepted() throws Exception {
        ListController controller = new ListController();
        MockMvc mvc = MockMvcBuilders.standaloneSetup(controller).addInterceptors(new PaginationRequestInterceptor()).build();
        mvc.perform(get("/list")).andExpect(status().isOk());
        mvc.perform(get("/list").param("pageNo", "1").param("pageSize", "1")).andExpect(status().isOk());
        mvc.perform(get("/list").param("pageNo", "2").param("pageSize", "100")).andExpect(status().isOk());
        assertEquals(3, controller.calls.get());
    }

    @Test public void invalidResponseIsActionableJsonAndSqlPluginHasHardLimit() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest(); request.addParameter("pageSize", "-1");
        MockHttpServletResponse response = new MockHttpServletResponse();
        assertFalse(new PaginationRequestInterceptor().preHandle(request, response, new Object()));
        assertTrue(response.getContentAsString().contains("\"success\":false"));
        assertEquals(100L, ReflectionTestUtils.getField(new MybatisPlusConfig().paginationInterceptor(), "limit"));
    }

    @Test public void realUserExportLoadsAll101UsersInStableBoundedPages() {
        ISysUserService service = mock(ISysUserService.class);
        List<SysUser> users = users(101);
        List<Long> requestedPages = new ArrayList<>();
        List<Long> requestedSizes = new ArrayList<>();
        when(service.getUserList(any(), any())).thenAnswer(invocation -> {
            Page<SysUser> page = invocation.getArgument(0);
            QueryWrapper<SysUser> query = invocation.getArgument(1);
            requestedPages.add(page.getCurrent());
            requestedSizes.add(page.getSize());
            assertTrue(query.getSqlSegment().contains("ORDER BY sys_user.id ASC"));
            int from = (int) ((page.getCurrent() - 1) * page.getSize());
            int to = Math.min(from + (int) page.getSize(), users.size());
            return new Page<SysUser>(page.getCurrent(), page.getSize(), users.size())
                .setRecords(new ArrayList<>(users.subList(from, to)));
        });
        when(service.getDepNamesByUserIds(anyList())).thenReturn(Collections.emptyMap());
        when(service.getRoleNamesByUserIds(anyList())).thenReturn(Collections.emptyMap());

        ModelAndView exported = exportUsers(service);
        @SuppressWarnings("unchecked")
        List<SysUser> exportedUsers = (List<SysUser>) exported.getModel().get(NormalExcelConstants.DATA_LIST);
        assertEquals(101, exportedUsers.size());
        List<String> expectedIds = new ArrayList<>();
        List<String> exportedIds = new ArrayList<>();
        for (SysUser user : users) expectedIds.add(user.getId());
        for (SysUser user : exportedUsers) exportedIds.add(user.getId());
        assertEquals(expectedIds, exportedIds);
        assertEquals(Arrays.asList(1L, 2L), requestedPages);
        assertEquals(Arrays.asList(100L, 100L), requestedSizes);
        verify(service).getDepNamesByUserIds(expectedIds);
        verify(service).getRoleNamesByUserIds(expectedIds);
    }

    @Test public void realUserExportRejectsEmptyLaterPageInsteadOfReturningPartialFile() {
        ISysUserService service = mock(ISysUserService.class);
        List<Long> requestedPages = new ArrayList<>();
        when(service.getUserList(any(), any())).thenAnswer(invocation -> {
            Page<SysUser> page = invocation.getArgument(0);
            requestedPages.add(page.getCurrent());
            assertEquals(100L, page.getSize());
            return new Page<SysUser>(page.getCurrent(), page.getSize(), 101)
                .setRecords(page.getCurrent() == 1 ? users(100) : Collections.emptyList());
        });
        try {
            exportUsers(service);
            fail("A missing later page must not return a partial export view");
        } catch (JeecgBootException expected) {
            assertTrue(expected.getMessage().contains("请重试"));
        }
        assertEquals(Arrays.asList(1L, 2L), requestedPages);
        verify(service, never()).getDepNamesByUserIds(anyList());
        verify(service, never()).getRoleNamesByUserIds(anyList());
    }

    @Test public void userExportRejectsChangedTotalsShortPagesAndDuplicates() {
        for (int scenario = 0; scenario < 3; scenario++) {
            final int variant = scenario;
            ISysUserService service = mock(ISysUserService.class);
            when(service.getUserList(any(), any())).thenAnswer(invocation -> {
                Page<SysUser> page = invocation.getArgument(0);
                if (page.getCurrent() == 1) return new Page<SysUser>(1, 100, 201).setRecords(users(100));
                List<SysUser> records = variant == 1 ? users(1) : users(100);
                return new Page<SysUser>(2, 100, variant == 0 ? 301 : 201).setRecords(records);
            });
            try { exportUsers(service); fail("Changing pages cannot produce a successful partial export"); }
            catch (JeecgBootException expected) { assertTrue(expected.getMessage().contains("请重试")); }
            verify(service, never()).getDepNamesByUserIds(anyList());
        }
    }

    private static List<SysUser> users(int count) {
        List<SysUser> users = new ArrayList<>();
        for (int index = 0; index < count; index++) {
            SysUser user = new SysUser();
            user.setId(String.format("user-%03d", index));
            users.add(user);
        }
        return users;
    }

    private static ModelAndView exportUsers(ISysUserService service) {
        SysUserController controller = new SysUserController();
        ReflectionTestUtils.setField(controller, "sysUserService", service);
        Subject subject = mock(Subject.class);
        LoginUser principal = new LoginUser();
        principal.setRealname("Synthetic exporter");
        when(subject.hasRole("admin")).thenReturn(true);
        when(subject.getPrincipal()).thenReturn(principal);
        Subject previousSubject = ThreadContext.getSubject();
        RequestAttributes previousRequest = RequestContextHolder.getRequestAttributes();
        MockHttpServletRequest request = new MockHttpServletRequest();
        ThreadContext.bind(subject);
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
        try {
            return controller.exportXls(new SysUserModel(), request);
        } finally {
            ThreadContext.unbindSubject();
            if (previousSubject != null) ThreadContext.bind(previousSubject);
            RequestContextHolder.setRequestAttributes(previousRequest);
        }
    }
}
