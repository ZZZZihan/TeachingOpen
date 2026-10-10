package org.jeecg.workintegrity;

import org.jeecg.common.api.vo.Result;
import org.jeecg.common.util.RedisUtil;
import org.jeecg.modules.teaching.controller.TeachingWorkController;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.jeecg.modules.teaching.service.ITeachingWorkService;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.junit.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Date;
import java.util.concurrent.*;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class WorkStarControllerTest {
    @Test public void savedContentCannotBeReplacedByTheSnapshotReadBeforeALike() throws Exception {
        for (String status : new String[]{"3", "1"}) {
            ITeachingWorkService service = mock(ITeachingWorkService.class);
            TeachingAccessService access = mock(TeachingAccessService.class); RedisUtil redis = mock(RedisUtil.class);
            TeachingWorkController controller = new TeachingWorkController();
            ReflectionTestUtils.setField(controller, "teachingWorkService", service);
            ReflectionTestUtils.setField(controller, "teachingAccessService", access);
            ReflectionTestUtils.setField(controller, "redisUtil", redis);
            TeachingWork old = new TeachingWork(); old.setId("work"); old.setWorkFile("old-file");
            old.setWorkStatus("3"); old.setUserId("owner"); old.setStarNum(7); old.setDelFlag(0);
            TeachingWork current = new TeachingWork(); current.setId("work"); current.setWorkFile("old-file");
            current.setUserId("owner"); current.setWorkStatus("3"); current.setStarNum(7);
            Date edited = new Date(10);
            CountDownLatch read = new CountDownLatch(1), continueLike = new CountDownLatch(1);
            when(service.getById("work")).thenReturn(old);
            doAnswer(call -> { read.countDown(); assertTrue(continueLike.await(5, TimeUnit.SECONDS)); return null; })
                    .when(access).requireCommunityWork(old);
            when(service.incrementStarCount("work")).thenAnswer(call -> {
                if (!"3".equals(current.getWorkStatus())) return false;
                current.setStarNum(current.getStarNum() + 1); return true;
            });
            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                Future<Result> reply = pool.submit(() -> controller.starWork("work", new MockHttpServletRequest()));
                assertTrue(read.await(5, TimeUnit.SECONDS));
                current.setWorkFile("new-file"); current.setWorkStatus(status);
                current.setUpdateBy("new-editor"); current.setUpdateTime(edited);
                continueLike.countDown();
                assertEquals("3".equals(status), reply.get(5, TimeUnit.SECONDS).isSuccess());
            } finally { continueLike.countDown(); pool.shutdownNow(); }
            assertEquals("new-file", current.getWorkFile()); assertEquals(status, current.getWorkStatus());
            assertEquals("owner", current.getUserId()); assertEquals("new-editor", current.getUpdateBy()); assertEquals(edited, current.getUpdateTime());
            assertEquals(Integer.valueOf("3".equals(status) ? 8 : 7), current.getStarNum());
            assertEquals("old-file", old.getWorkFile()); assertEquals(Integer.valueOf(7), old.getStarNum());
            verify(service).incrementStarCount("work"); verify(service, never()).updateById(any());
            if ("1".equals(status)) verify(redis, never()).set(anyString(), any(), anyLong());
        }
    }

    @Test public void privateWorkCannotBeLikedEvenByAnAuthorizedReader() {
        ITeachingWorkService service = mock(ITeachingWorkService.class); RedisUtil redis = mock(RedisUtil.class);
        TeachingWorkController controller = new TeachingWorkController();
        ReflectionTestUtils.setField(controller, "teachingWorkService", service);
        ReflectionTestUtils.setField(controller, "teachingAccessService", mock(TeachingAccessService.class));
        ReflectionTestUtils.setField(controller, "redisUtil", redis);
        TeachingWork privateWork = new TeachingWork(); privateWork.setWorkStatus("0");
        when(service.getById("work")).thenReturn(privateWork);
        assertFalse(controller.starWork("work", new MockHttpServletRequest()).isSuccess());
        verify(service, never()).incrementStarCount(anyString()); verifyZeroInteractions(redis);
    }
}
