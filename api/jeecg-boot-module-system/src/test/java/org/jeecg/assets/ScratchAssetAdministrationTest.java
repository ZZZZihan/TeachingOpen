package org.jeecg.assets;

import com.alibaba.fastjson.JSONArray;
import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.poi.hssf.usermodel.HSSFWorkbook;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.exception.JeecgBootExceptionHandler;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.*;
import org.jeecg.modules.system.service.GlobalResourceAccessService;
import org.jeecg.modules.teaching.controller.TeachingScratchAssetsController;
import org.jeecg.modules.teaching.entity.TeachingScratchAssets;
import org.jeecg.modules.teaching.mapper.TeachingScratchAssetsMapper;
import org.jeecg.modules.teaching.service.ScratchAssetValidator;
import org.jeecg.modules.teaching.service.impl.TeachingScratchAssetsServiceImpl;
import org.junit.*;
import org.mockito.ArgumentCaptor;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import java.io.ByteArrayOutputStream;
import java.nio.file.*;
import java.util.*;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

public class ScratchAssetAdministrationTest {
    private Subject subject;
    private SysUser actor;
    private SysUserMapper users;
    private SysUserRoleMapper roles;
    private TeachingScratchAssetsMapper mapper;
    private TeachingScratchAssetsServiceImpl service;
    private TeachingScratchAssetsController controller;
    private MockMvc http;
    private static final String BASE="/teaching/teachingScratchAssets";
    private static final String IMAGE="{\"name\":\"Fixture\",\"tags\":[],\"assetId\":\"abcd\",\"dataFormat\":\"svg\",\"md5ext\":\"abcd.svg\",\"bitmapResolution\":1,\"rotationCenterX\":1,\"rotationCenterY\":1}";

    @Before public void setup() {
        users=mock(SysUserMapper.class); roles=mock(SysUserRoleMapper.class); mapper=mock(TeachingScratchAssetsMapper.class);
        GlobalResourceAccessService access=new GlobalResourceAccessService(users,roles);
        actor=new SysUser().setId("actor").setUsername("manager").setStatus(1).setDelFlag(0);
        LoginUser principal=new LoginUser(); principal.setId("actor");
        subject=mock(Subject.class); when(subject.getPrincipal()).thenReturn(principal); ThreadContext.bind(subject);
        when(users.selectById("actor")).thenReturn(actor); when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("admin"));
        when(subject.hasRole(anyString())).thenReturn(true); // A stale grant must never be consulted.
        service=new TeachingScratchAssetsServiceImpl(); ReflectionTestUtils.setField(service,"access",access);
        ReflectionTestUtils.setField(service,"baseMapper",mapper);
        when(mapper.insert(any(TeachingScratchAssets.class))).thenReturn(1);
        when(mapper.updateById(any(TeachingScratchAssets.class))).thenReturn(1);
        when(mapper.selectById("existing")).thenReturn(asset().setId("existing"));
        controller=new TeachingScratchAssetsController();
        ReflectionTestUtils.setField(controller,"teachingScratchAssetsService",service);
        ReflectionTestUtils.setField(controller,"service",service); ReflectionTestUtils.setField(controller,"access",access);
        http=MockMvcBuilders.standaloneSetup(controller).setControllerAdvice(new JeecgBootExceptionHandler()).build();
    }
    private TeachingScratchAssets asset() { return new TeachingScratchAssets().setAssetType(1).setAssetName("Fixture").setAssetData(IMAGE); }
    @After public void cleanup() { ThreadContext.remove(); }

    @Test public void studentCannotSaveSharedAssetBeforeAnyMapperWrite() {
        when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("student"));
        denied(() -> service.save(asset())); verifyZeroInteractions(mapper);
    }

    @Test public void studentTeacherAndRevokedCachedRolesDenyEveryServiceMutation() {
        for (List<String> grants : Arrays.asList(Arrays.asList("student"),Arrays.asList("teacher"), Collections.<String>emptyList())) {
            when(roles.getRoleByUserId("actor")).thenReturn(grants);
            denied(() -> service.save(asset())); denied(() -> service.updateById(asset().setId("existing")));
            denied(() -> service.saveBatch(Arrays.asList(asset()))); denied(() -> service.removeById("existing"));
            denied(() -> service.removeByIds(Arrays.asList("existing")));
            denied(() -> service.update(asset(),null)); denied(() -> service.removeByMap(Collections.emptyMap()));
            denied(() -> service.saveOrUpdate(asset())); denied(() -> service.updateBatchById(Arrays.asList(asset())));
        }
        verifyZeroInteractions(mapper); verify(subject,never()).hasRole(anyString());
    }

    @Test public void controllerDeniesAllManagementRoutesBeforeStateAccess() throws Exception {
        for (String role : Arrays.asList("student","teacher")) {
            when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList(role));
            for (org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request : Arrays.asList(
                    get(BASE+"/list"),get(BASE+"/queryById").param("id","existing"),get(BASE+"/exportXls"),
                    post(BASE+"/add").contentType("application/json").content("{}"),
                    put(BASE+"/edit").contentType("application/json").content("{}"),
                    delete(BASE+"/delete").param("id","existing"),delete(BASE+"/deleteBatch").param("ids","existing,second"),
                    post(BASE+"/importExcel"))) {
                http.perform(request).andExpect(jsonPath("$.success").value(false)).andExpect(jsonPath("$.code").value(510));
            }
        }
        verifyZeroInteractions(mapper);
    }

    @Test public void samePrincipalRevocationAndFrozenAccountsTakeEffectImmediately() {
        service.save(asset()); clearInvocations(mapper);
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.emptyList()); denied(() -> service.save(asset()));
        when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("admin"));
        actor.setStatus(2); denied(() -> service.removeById("existing")); actor.setStatus(1).setDelFlag(1);
        denied(() -> service.saveBatch(Arrays.asList(asset()))); when(subject.getPrincipal()).thenReturn(null);
        denied(() -> service.save(asset())); verifyZeroInteractions(mapper);
    }

    @Test public void bothManagerRolesCanCrudAndOnlyEditableColumnsReachMapper() {
        for (String role : Arrays.asList("admin","dev")) {
            when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList(role));
            service.save(asset().setId("forged").setCreateBy("other").setUpdateBy("other").setDelFlag(1));
            service.updateById(asset().setId("existing").setCreateBy("other").setCreateTime(new Date(1)).setDelFlag(1));
            service.removeById("existing"); service.removeByIds(Arrays.asList("existing","second"));
        }
        ArgumentCaptor<TeachingScratchAssets> created=ArgumentCaptor.forClass(TeachingScratchAssets.class);
        verify(mapper,times(2)).insert(created.capture());
        for (TeachingScratchAssets row : created.getAllValues()) {
            assertNotEquals("forged",row.getId()); assertEquals("manager",row.getCreateBy()); assertEquals(Integer.valueOf(0),row.getDelFlag()); assertNull(row.getUpdateBy());
        }
        ArgumentCaptor<TeachingScratchAssets> updated=ArgumentCaptor.forClass(TeachingScratchAssets.class);
        verify(mapper,times(2)).updateById(updated.capture());
        for (TeachingScratchAssets row : updated.getAllValues()) { assertNull(row.getCreateBy()); assertNull(row.getCreateTime()); assertNull(row.getDelFlag()); assertEquals("manager",row.getUpdateBy()); }
        verify(mapper,times(4)).deleteBatchIds(anyCollection());
    }

    @Test public void invalidImportRowRejectsWholeBatchBeforeAnyWrite() {
        for (String bad : Arrays.asList("{","[]","null",IMAGE+"{}",IMAGE.replace("\"tags\":[]","\"tags\":{},\"unknown\":1"),
                IMAGE.replace("abcd.svg","../abcd.svg"), IMAGE.replace("\"bitmapResolution\":1","\"bitmapResolution\":0"))) {
            invalid(() -> service.saveBatch(Arrays.asList(asset(),asset().setAssetData(bad))));
        }
        invalid(() -> service.save(asset().setAssetType(5))); invalid(() -> service.save(asset().setMd5Ext("other.svg")));
        verifyZeroInteractions(mapper);
    }

    @Test public void realExcelImportUsesSameValidationAndAllowsAdminAndDev() throws Exception {
        for (String role : Arrays.asList("admin","dev")) {
            when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList(role));
            http.perform(multipart(BASE+"/importExcel").file(workbook(IMAGE)))
                    .andExpect(jsonPath("$.success").value(true));
        }
        verify(mapper,times(2)).insert(any(TeachingScratchAssets.class)); clearInvocations(mapper);
        http.perform(multipart(BASE+"/importExcel").file(workbook(IMAGE,"{")))
                .andExpect(jsonPath("$.success").value(false));
        verifyZeroInteractions(mapper);
    }
    private MockMultipartFile workbook(String... data) throws Exception {
        HSSFWorkbook book=new HSSFWorkbook();
        try (ByteArrayOutputStream output=new ByteArrayOutputStream()) {
            Sheet sheet=book.createSheet("素材"); sheet.createRow(0).createCell(0).setCellValue("素材库");
            sheet.createRow(1).createCell(0).setCellValue("回归"); Row header=sheet.createRow(2);
            String[] headers={"素材类型 1背景 2声音 3造型 4角色","冗余 素材名","素材json数据"};
            for (int i=0;i<headers.length;i++) header.createCell(i).setCellValue(headers[i]);
            for (int i=0;i<data.length;i++) { Row row=sheet.createRow(i+3); row.createCell(0).setCellValue(1); row.createCell(1).setCellValue("Fixture"); row.createCell(2).setCellValue(data[i]); }
            book.write(output); return new MockMultipartFile("file","assets.xls","application/vnd.ms-excel",output.toByteArray());
        }
    }

    @Test public void oneHistoricalMalformedRowCannotBreakWholeStudentLibrary() throws Exception {
        when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("student"));
        when(mapper.selectList(any(Wrapper.class))).thenReturn(Arrays.asList(
                new TeachingScratchAssets().setId("bad").setAssetType(1).setAssetData("{"),asset().setId("good")));
        JSONArray result=controller.getScratchAssets(1);
        assertEquals(1,result.size()); assertEquals("Fixture",result.getJSONObject(0).getString("name"));
        http.perform(get(BASE+"/getScratchAssets").param("assetType","1")).andExpect(status().isOk()).andExpect(jsonPath("$[0].name").value("Fixture"));
    }

    @Test public void repositoryScratchLibrariesRemainCompatibleWithAllowedShapes() throws Exception {
        Path repo=Paths.get("../.."); ObjectMapper json=new ObjectMapper();
        String[] names={"backdrops","sounds","costumes","sprites"};
        for (int i=0;i<names.length;i++) {
            JsonNode rows=json.readTree(repo.resolve("web/public/scratch3/static/json_index/"+names[i]+".json").toFile());
            assertTrue(rows.size()>0);
            for (JsonNode row : rows) ScratchAssetValidator.parse(i+1,row.toString());
        }
    }
    private void denied(Runnable call) { try { call.run(); fail("Denied operation accepted"); } catch (UnauthorizedException expected) { } }
    private void invalid(Runnable call) { try { call.run(); fail("Invalid data accepted"); } catch (JeecgBootException expected) { } }
}
