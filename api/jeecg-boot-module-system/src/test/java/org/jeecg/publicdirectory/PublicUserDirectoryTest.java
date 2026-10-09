package org.jeecg.publicdirectory;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.jeecg.modules.teaching.mapper.PublicUserDirectoryMapper;
import org.jeecg.modules.teaching.service.PublicUserDirectoryService;
import org.jeecg.modules.teaching.vo.PublicUserDirectory;
import org.junit.Test;
import java.util.Collections;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;

public class PublicUserDirectoryTest {
    @Test public void masksNamesByUnicodeCodePoint() {
        assertEquals("张*", PublicUserDirectoryService.maskName("张三"));
        assertEquals("王*明", PublicUserDirectoryService.maskName("王小明"));
        assertEquals("欧**娜", PublicUserDirectoryService.maskName("欧阳娜娜"));
        assertEquals("*", PublicUserDirectoryService.maskName("王"));
        assertEquals("*", PublicUserDirectoryService.maskName(null));
        assertEquals("𠮷*", PublicUserDirectoryService.maskName(" 𠮷三 "));
    }
    @Test public void clampsPageAndSerializesOnlyPublicFields() throws Exception {
        PublicUserDirectoryMapper mapper = mock(PublicUserDirectoryMapper.class);
        when(mapper.countRegisteredUsers()).thenReturn(11L);
        PublicUserDirectoryMapper.RegisteredUser row = new PublicUserDirectoryMapper.RegisteredUser();
        row.setRealname("王小明"); row.setSchool("某某完整学校名称"); row.setIdentity("student");
        when(mapper.listRegisteredUsers(10L)).thenReturn(Collections.singletonList(row));
        PublicUserDirectory result = new PublicUserDirectoryService(mapper).load(Long.MAX_VALUE);
        assertEquals(2L, result.getPageNo()); assertEquals(10, result.getPageSize());
        String json = new ObjectMapper().writeValueAsString(result);
        assertTrue(json.contains("王*明")); assertTrue(json.contains("某某完整学校名称"));
        assertFalse(json.contains("王小明"));
        assertEquals(3, new ObjectMapper().readTree(json).get("records").get(0).size());
        verify(mapper).listRegisteredUsers(10L);
    }
    @Test public void emptyAndNegativePageUseFirstPage() {
        PublicUserDirectoryMapper mapper = mock(PublicUserDirectoryMapper.class);
        when(mapper.listRegisteredUsers(0L)).thenReturn(Collections.emptyList());
        PublicUserDirectory result = new PublicUserDirectoryService(mapper).load(-1L);
        assertEquals(1L, result.getPageNo()); assertEquals(0L, result.getTotal()); assertTrue(result.getRecords().isEmpty());
    }
}
