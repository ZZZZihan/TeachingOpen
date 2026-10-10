package org.jeecg.additionalwork;

import org.jeecg.modules.teaching.controller.TeachingDepartDayLogController;
import org.jeecg.modules.teaching.service.ITeachingCourseUnitService;
import org.jeecg.modules.teaching.service.ITeachingDepartDayLogService;
import org.jeecg.common.util.RedisUtil;
import org.junit.Before;
import org.junit.Test;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** The generated write routes must never reach counters or the inherited importer. */
public class TeachingDepartDayLogWriteBoundaryTest {
    private MockMvc http;
    private ITeachingDepartDayLogService logs;
    private ITeachingCourseUnitService units;
    private RedisUtil redis;
    private static final String BASE = "/teaching/teachingDepartDayLog";

    @Before public void setup() {
        TeachingDepartDayLogController controller = new TeachingDepartDayLogController();
        logs = mock(ITeachingDepartDayLogService.class);
        units = mock(ITeachingCourseUnitService.class);
        redis = mock(RedisUtil.class);
        ReflectionTestUtils.setField(controller, "teachingDepartDayLogService", logs);
        ReflectionTestUtils.setField(controller, "teachingCourseUnitService", units);
        ReflectionTestUtils.setField(controller, "redisUtil", redis);
        // Inject the inherited import service too, so a regression into importExcel
        // cannot fail merely because the base controller was not wired.
        ReflectionTestUtils.setField(controller, "service", logs);
        http = MockMvcBuilders.standaloneSetup(controller).build();
    }

    @Test public void addCannotCreateAManualDayRow() throws Exception {
        http.perform(post(BASE + "/add").contentType("application/json")
                .content("{\"departId\":\"class-a\",\"createTime\":\"2026-10-11\",\"unitOpenCount\":999}"))
                .andExpect(status().isForbidden()).andExpect(jsonPath("$.success").value(false))
                .andExpect(jsonPath("$.code").value(403));
        verifyZeroInteractions(logs, units, redis);
    }

    @Test public void editCannotRewriteEventCounters() throws Exception {
        http.perform(put(BASE + "/edit").contentType("application/json")
                .content("{\"id\":\"existing-day\",\"additionalWorkAssignCount\":999}"))
                .andExpect(status().isForbidden()).andExpect(jsonPath("$.code").value(403));
        verifyZeroInteractions(logs, units, redis);
    }

    @Test public void deleteCannotRemoveADayRow() throws Exception {
        http.perform(delete(BASE + "/delete").param("id", "existing-day"))
                .andExpect(status().isForbidden()).andExpect(jsonPath("$.code").value(403));
        verifyZeroInteractions(logs, units, redis);
    }

    @Test public void batchDeleteCannotRemoveDayRows() throws Exception {
        http.perform(delete(BASE + "/deleteBatch").param("ids", "existing-day,another-day"))
                .andExpect(status().isForbidden()).andExpect(jsonPath("$.code").value(403));
        verifyZeroInteractions(logs, units, redis);
    }

    @Test public void importCannotEnterTheInheritedExcelWriter() throws Exception {
        http.perform(multipart(BASE + "/importExcel").file(new MockMultipartFile(
                "file", "manual-day.xls", "application/vnd.ms-excel", new byte[]{1, 2, 3})))
                .andExpect(status().isForbidden()).andExpect(jsonPath("$.success").value(false))
                .andExpect(jsonPath("$.code").value(403))
                .andExpect(jsonPath("$.message").value("班级每日教学记录由教学事件自动生成，不支持人工修改"));
        verifyZeroInteractions(logs, units, redis);
    }
}
