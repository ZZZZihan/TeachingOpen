package org.jeecg.management;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.minio.MinioClient;
import java.io.ByteArrayOutputStream;
import java.util.*;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.MinioUtil;
import org.jeecg.common.util.SpringContextUtils;
import org.jeecg.config.*;
import org.jeecg.modules.monitor.controller.ActuatorRedisController;
import org.jeecg.modules.monitor.domain.RedisInfo;
import org.jeecg.modules.monitor.service.RedisService;
import org.jeecg.modules.oss.controller.OSSFileController;
import org.jeecg.modules.oss.entity.OSSFile;
import org.jeecg.modules.oss.service.IOSSFileService;
import org.jeecg.modules.system.controller.*;
import org.jeecg.modules.system.entity.*;
import org.jeecg.modules.system.mapper.*;
import org.jeecg.modules.system.service.*;
import org.junit.*;
import org.junit.runner.RunWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.*;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit4.SpringJUnit4ClassRunner;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Uses the application's actual MVC registration, not a test-only interceptor chain. */
@RunWith(SpringJUnit4ClassRunner.class)
@WebAppConfiguration
@ContextConfiguration(classes = GlobalManagementAuthorizationTest.Config.class)
@TestPropertySource(properties = {"jeecg.path.webapp=/tmp/teachingopen-management-test/", "jeecg.path.upload=/tmp/teachingopen-management-test/", "spring.resource.static-locations=classpath:/static/"})
public class GlobalManagementAuthorizationTest {
    @Configuration @EnableWebMvc
    @Import({WebMvcConfiguration.class, GlobalManagementInterceptor.class, InfrastructureManagementInterceptor.class,
            SysUserAgentController.class, SysPositionController.class, OSSFileController.class,
            SysUploadController.class, ActuatorRedisController.class, SpringContextUtils.class})
    public static class Config {
        @Bean public SysUserMapper users() { return mock(SysUserMapper.class); }
        @Bean public SysUserRoleMapper roles() { return mock(SysUserRoleMapper.class); }
        @Bean public ISysUserAgentService agents() { return mock(ISysUserAgentService.class); }
        @Bean public ISysPositionService positions() { return mock(ISysPositionService.class); }
        @Bean public IOSSFileService files() { return mock(IOSSFileService.class); }
        @Bean public RedisService redis() { return mock(RedisService.class); }
        @Bean public ISysPermissionService permissions() { return mock(ISysPermissionService.class); }
        @Bean public UserQueryAccessService accounts(SysUserMapper users, SysUserRoleMapper roles) {
            return new UserQueryAccessService(users, roles, mock(SysDepartMapper.class), mock(ISysDepartService.class));
        }
        @Bean public InfrastructureAccessService infrastructure(SysUserMapper users, SysUserRoleMapper roles) {
            return new InfrastructureAccessService(users, roles);
        }
    }

    @Autowired private WebApplicationContext context;
    @Autowired private SysUserMapper users;
    @Autowired private SysUserRoleMapper roles;
    @Autowired private ISysUserAgentService agents;
    @Autowired private ISysPositionService positions;
    @Autowired private IOSSFileService files;
    @Autowired private RedisService redis;
    private MockMvc http;
    private Subject subject;
    private SysUser actor;
    private MinioClient cloud;
    private final Map<String,Object> oldMinio = new HashMap<>();
    private static final String MARKER = "fixture-management-private-marker";
    private static Object previousContext;

    @BeforeClass public static void headless() {
        System.setProperty("java.awt.headless", "true");
        previousContext = SpringContextUtils.getApplicationContext();
    }
    @AfterClass public static void restoreContext() {
        ReflectionTestUtils.setField(SpringContextUtils.class, "applicationContext", previousContext);
    }

    @Before public void setup() throws Exception {
        reset(users, roles, agents, positions, files, redis);
        for (Class<?> type : Arrays.asList(SysUserAgent.class, SysPosition.class, OSSFile.class))
            TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new MybatisConfiguration(), "management-test"), type);
        actor = new SysUser().setId("actor").setUsername("fixture_manager").setStatus(1).setDelFlag(0);
        LoginUser identity = new LoginUser(); identity.setId("actor"); identity.setUsername("stale-name"); identity.setRealname("Fixture");
        subject = mock(Subject.class); when(subject.getPrincipal()).thenReturn(identity); ThreadContext.bind(subject);
        when(users.selectById("actor")).thenReturn(actor); role("admin");
        SysUserAgent agent = new SysUserAgent(); agent.setId("agent"); agent.setUserName("fixture_owner"); agent.setAgentUserName(MARKER);
        SysPosition position = new SysPosition().setId("position").setName("Fixture position").setCode("fixture_position");
        OSSFile file = new OSSFile(); file.setId("file"); file.setFileName(MARKER); file.setUrl("http://127.0.0.1:1/synthetic");
        when(agents.page(any(Page.class), any())).thenReturn(new Page<SysUserAgent>(1,10).setRecords(Collections.singletonList(agent)));
        when(positions.page(any(Page.class), any())).thenReturn(new Page<SysPosition>(1,10).setRecords(Collections.singletonList(position)));
        when(files.page(any(Page.class), any())).thenReturn(new Page<OSSFile>(1,10).setRecords(Collections.singletonList(file)));
        when(agents.getById(anyString())).thenReturn(agent); when(agents.getOne(any())).thenReturn(agent);
        when(positions.getById(anyString())).thenReturn(position); when(files.getById(anyString())).thenReturn(file);
        when(agents.list(any())).thenReturn(Collections.emptyList()); when(positions.list(any())).thenReturn(Collections.emptyList());
        when(agents.save(any())).thenReturn(true); when(agents.updateById(any())).thenReturn(true);
        when(agents.removeById(anyString())).thenReturn(true); when(agents.removeByIds(anyCollection())).thenReturn(true);
        when(positions.save(any())).thenReturn(true); when(positions.updateById(any())).thenReturn(true);
        when(positions.removeById(anyString())).thenReturn(true); when(positions.removeByIds(anyCollection())).thenReturn(true);
        when(files.save(any())).thenReturn(true); when(files.delete(any())).thenReturn(true);
        RedisInfo info = new RedisInfo(); info.setKey("redis_version"); info.setValue(MARKER);
        when(redis.getRedisInfo()).thenReturn(Collections.singletonList(info));
        when(redis.getKeysSize()).thenReturn(Collections.<String,Object>singletonMap("dbSize", 1));
        when(redis.getMemoryInfo()).thenReturn(Collections.<String,Object>singletonMap("used_memory", 1));
        // Both allowed and regression-baseline upload calls are isolated from real cloud services.
        for (String field : Arrays.asList("minioClient", "minioUrl", "bucketName")) oldMinio.put(field, ReflectionTestUtils.getField(MinioUtil.class, field));
        cloud = mock(MinioClient.class); when(cloud.bucketExists("fixture")).thenReturn(true);
        ReflectionTestUtils.setField(MinioUtil.class, "minioClient", cloud);
        MinioUtil.setMinioUrl("http://127.0.0.1:1/"); MinioUtil.setBucketName("fixture");
        http = MockMvcBuilders.webAppContextSetup(context).defaultRequest(get("/").header("User-Agent", "FixtureMvc")).build();
    }
    @After public void cleanup() {
        ThreadContext.unbindSubject();
        oldMinio.forEach((field,value) -> ReflectionTestUtils.setField(MinioUtil.class,field,value));
    }
    private void role(String role) { when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList(role)); }
    private void denied(MockHttpServletRequestBuilder request) throws Exception {
        http.perform(request).andExpect(status().isForbidden()).andExpect(jsonPath("$.code").value(403))
                .andExpect(jsonPath("$.success").value(false)).andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString(MARKER))));
    }
    private void unchanged() { verifyZeroInteractions(agents, positions, files, redis, cloud); }
    private List<MockHttpServletRequestBuilder> management() throws Exception {
        return Arrays.asList(get("/sys/sysUserAgent/list"),get("/sys/sysUserAgent/queryById?id=agent"),
                get("/sys/sysUserAgent/queryByUserName?userName=fixture_owner"),get("/sys/sysUserAgent/exportXls"),
                post("/sys/sysUserAgent/add").contentType("application/json").content("{\"userName\":\"fixture_owner\"}"),
                put("/sys/sysUserAgent/edit").contentType("application/json").content("{\"id\":\"agent\"}"),
                delete("/sys/sysUserAgent/delete?id=agent"),delete("/sys/sysUserAgent/deleteBatch?ids=agent,other"),
                multipart("/sys/sysUserAgent/importExcel").file(xlsx("userAgent")),
                get("/sys/position/queryById?id=position"),get("/sys/position/exportXls"),
                post("/sys/position/add").contentType("application/json").content("{\"code\":\"fixture_new\"}"),
                put("/sys/position/edit").contentType("application/json").content("{\"id\":\"position\"}"),
                delete("/sys/position/delete?id=position"),delete("/sys/position/deleteBatch?ids=position,other"),
                multipart("/sys/position/importExcel").file(xlsx("position")),
                get("/oss/file/list"),get("/oss/file/queryById?id=file"),delete("/oss/file/delete?id=file"),
                multipart("/oss/file/upload").file(upload()),multipart("/sys/upload/uploadMinio").file(upload()));
    }
    private List<String> monitor() { return Arrays.asList("info", "keysSize", "memoryInfo", "queryDiskInfo"); }

    @Test public void ordinaryManagementReadsWritesImportsAndDeletesAreDeniedBeforeAnyServiceCall() throws Exception {
        for (String role : Arrays.asList("student", "teacher", "unassigned")) {
            role(role); for (MockHttpServletRequestBuilder request : management()) denied(request);
        }
        unchanged();
    }
    @Test public void anonymousAndSuffixAliasesCannotEnterManagementHandlers() throws Exception {
        when(subject.getPrincipal()).thenReturn(null);
        for (MockHttpServletRequestBuilder request : management()) denied(request);
        for (String suffix : Arrays.asList(".js", "/", ";version=1")) {
            denied(get("/sys/sysUserAgent/list"+suffix)); denied(delete("/oss/file/delete"+suffix+"?id=file"));
            denied(post("/sys/position/add"+suffix).contentType("application/json").content("{\"code\":\"new\"}"));
            denied(get("/actuator/redis/info"+suffix));
        }
        unchanged();
    }
    @Test public void addressBookAndPositionSelectorKeepTheirAuthenticatedList() throws Exception {
        for (String role : Arrays.asList("student", "teacher", "admin", "dev")) {
            role(role); http.perform(get("/sys/position/list")).andExpect(status().isOk()).andExpect(jsonPath("$.result.records[0].name").value("Fixture position"));
        }
        verify(positions,times(4)).page(any(Page.class),any()); verifyZeroInteractions(agents,files,redis,cloud);
    }
    @Test public void anonymousAndInactiveAccountsCannotUsePositionListAliases() throws Exception {
        when(subject.getPrincipal()).thenReturn(null); denied(get("/sys/position/list.js"));
        LoginUser identity = new LoginUser(); identity.setId("actor"); when(subject.getPrincipal()).thenReturn(identity);
        actor.setStatus(2); denied(get("/sys/position/list"));
        actor.setStatus(1).setDelFlag(1); denied(get("/sys/position/list/"));
        when(users.selectById("actor")).thenReturn(null); denied(get("/sys/position/list")); unchanged();
    }
    @Test public void activeAdministratorsAndDevelopersRetainAllManagementOperations() throws Exception {
        for (String role : Arrays.asList("admin", "dev")) {
            role(role); for (MockHttpServletRequestBuilder request : management()) {
                org.springframework.test.web.servlet.MvcResult result = http.perform(request).andExpect(status().isOk()).andReturn();
                if (result.getModelAndView() == null)
                    assertTrue(com.alibaba.fastjson.JSON.parseObject(result.getResponse().getContentAsString()).getBooleanValue("success"));
                else assertTrue(result.getResponse().getContentAsByteArray().length > 100);
            }
        }
        verify(agents,times(4)).save(any()); verify(positions,times(4)).save(any());
        verify(agents,times(2)).removeById("agent"); verify(positions,times(2)).removeByIds(anyCollection());
        verify(files,times(2)).delete(any()); verify(files,times(2)).upload(any()); verify(files,times(2)).save(any());
        verify(cloud,times(2)).bucketExists("fixture");
    }
    @Test public void samePrincipalLosesAllManagementImmediatelyAfterRoleRevocation() throws Exception {
        http.perform(get("/sys/sysUserAgent/list")).andExpect(status().isOk());
        clearInvocations(agents,positions,files,redis,cloud); role("teacher");
        for (MockHttpServletRequestBuilder request : management()) denied(request); unchanged();
    }
    @Test public void disabledDeletedMissingAndMismatchedManagerAccountsCannotReachManagement() throws Exception {
        actor.setStatus(2); denied(delete("/oss/file/delete?id=file"));
        actor.setStatus(1).setDelFlag(1); denied(post("/sys/sysUserAgent/add").contentType("application/json").content("{}"));
        when(users.selectById("actor")).thenReturn(null); denied(get("/sys/position/exportXls"));
        when(users.selectById("actor")).thenReturn(new SysUser().setId("different").setStatus(1).setDelFlag(0));
        denied(delete("/sys/position/delete?id=position")); unchanged();
    }
    @Test public void redisOperationalMetadataRequiresDeveloperIncludingAdminRefusal() throws Exception {
        for (String role : Arrays.asList("student", "teacher", "admin", "unassigned")) {
            role(role); for (String route : monitor()) denied(get("/actuator/redis/"+route));
        }
        unchanged();
    }
    @Test public void developerMonitoringWorksAndSamePrincipalRevocationStopsIt() throws Exception {
        role("dev"); for (String route : monitor()) http.perform(get("/actuator/redis/"+route)).andExpect(status().isOk());
        verify(redis).getRedisInfo(); verify(redis).getKeysSize(); verify(redis).getMemoryInfo();
        clearInvocations(redis); role("admin");
        for (String route : monitor()) denied(get("/actuator/redis/"+route)); unchanged();
    }
    @Test public void disabledDeveloperCannotReadOperationalMetadata() throws Exception {
        role("dev"); actor.setStatus(2); for (String route : monitor()) denied(get("/actuator/redis/"+route)); unchanged();
    }
    private MockMultipartFile upload() { return new MockMultipartFile("file","fixture.txt","text/plain",MARKER.getBytes(java.nio.charset.StandardCharsets.UTF_8)); }
    private MockMultipartFile xlsx(String kind) throws Exception {
        Workbook book = new XSSFWorkbook();
        try (ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            Sheet sheet = book.createSheet("fixture"); sheet.createRow(0).createCell(0).setCellValue("Fixture title");
            sheet.createRow(1).createCell(0).setCellValue("Fixture subtitle");
            Row header = sheet.createRow(2); Row data = sheet.createRow(3);
            if ("position".equals(kind)) {
                header.createCell(0).setCellValue("职务编码"); header.createCell(1).setCellValue("职务名称");
                data.createCell(0).setCellValue("fixture_import"); data.createCell(1).setCellValue("Fixture import position");
            } else {
                header.createCell(0).setCellValue("用户名"); header.createCell(1).setCellValue("代理人用户名");
                data.createCell(0).setCellValue("fixture_owner"); data.createCell(1).setCellValue("fixture_delegate");
            }
            book.write(out); return new MockMultipartFile("file","fixture.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",out.toByteArray());
        }
    }
}
