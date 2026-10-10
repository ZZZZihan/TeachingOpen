package org.jeecg.modules.teaching.controller;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.lang.StringUtils;
import org.apache.shiro.SecurityUtils;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.aspect.annotation.AutoLog;
import org.jeecg.common.system.base.controller.JeecgController;
import org.jeecg.common.system.query.QueryGenerator;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.RedisUtil;
import org.jeecg.modules.teaching.entity.TeachingDepartDayLog;
import org.jeecg.modules.teaching.enums.DepartDayLogType;
import org.jeecg.modules.teaching.service.ITeachingCourseUnitService;
import org.jeecg.modules.teaching.service.ITeachingDepartDayLogService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.ModelAndView;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.util.List;

/**
* @Description: 班级每日教学记录
* @Author: jeecg-boot
* @Date:   2021-06-25
* @Version: V1.0
*/
@Api(tags="班级每日教学记录")
@RestController
@RequestMapping("/teaching/teachingDepartDayLog")
@Slf4j
public class TeachingDepartDayLogController extends JeecgController<TeachingDepartDayLog, ITeachingDepartDayLogService> {
   @Autowired
   private ITeachingDepartDayLogService teachingDepartDayLogService;
   @Autowired
   private ITeachingCourseUnitService teachingCourseUnitService;
   @Autowired
   private RedisUtil redisUtil;

   @GetMapping("unitViewLog")
   public Result<?> unitViewLog(@RequestParam String unitId){
       String departId = teachingCourseUnitService.getUserDepartIdByUnitId(getCurrentUser().getId(), unitId);
       String key = String.format("departLog:unitView:%s", departId);
       if (getCurrentUser().getUserIdentity().equals(2)){
            if (!redisUtil.sHasKey(key, unitId)){
                redisUtil.sSet(key, unitId);
                teachingDepartDayLogService.addLog(departId, DepartDayLogType.UNIT_OPEN_COUNT);
            }
       }
       return Result.ok();
   }

    /**
     * 获取每日教学记录
     * @param startTime
     * @param endTime
     * @return
     * unit_open_count
     * course_work_assign_count additional_work_assign_count
     * course_work_correct_count additional_work_correct_count
     * course_work_submit_count additional_work_submit_count
     */
    @ApiOperation(value="获取每日教学记录", notes="获取每日教学记录")
   @GetMapping("getReport")
   public Result<?> getReport(@RequestParam(required = false) String startTime,
                              @RequestParam(required = false) String endTime){
       //获取我负责的班级
       LoginUser user = (LoginUser) SecurityUtils.getSubject().getPrincipal();
       String departIds = user.getDepartIds();
       boolean isAdmin = hasRole("admin") || hasRole("dev");

       TeachingDepartDayLog report = teachingDepartDayLogService.getOne(new QueryWrapper<TeachingDepartDayLog>()
               .select("depart_id, depart_name, sum(unit_open_count) unit_open_count," +
                       "sum(course_work_assign_count) course_work_assign_count," +
                       "sum(additional_work_assign_count) additional_work_assign_count," +
                       "sum(course_work_correct_count) course_work_correct_count," +
                       "sum(additional_work_correct_count) additional_work_correct_count," +
                       "sum(course_work_submit_count) course_work_submit_count,"+
                       "sum(additional_work_submit_count) additional_work_submit_count"
               )
                       .in(!isAdmin, "depart_id", departIds.split(","))
                       .ge(StringUtils.isNotEmpty(startTime), "create_time", startTime)
                       .le(StringUtils.isNotEmpty(endTime), "create_time", endTime)
       );
       return Result.ok(report);
   }

    /**
     * 按班级聚合每日教学记录
     * @param startTime
     * @param endTime
     * @param pageNo
     * @param pageSize
     * @return
     */
    @ApiOperation(value="按班级聚合每日教学记录", notes="按班级聚合每日教学记录")
    @GetMapping("getReportGroupByDepart")
    public Result<?> getReportGroupByDepart(@RequestParam(required = false) String startTime,
                               @RequestParam(required = false) String endTime,
                                            @RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
                                            @RequestParam(name="pageSize", defaultValue="10") Integer pageSize){
        //获取我负责的班级
        LoginUser user = (LoginUser) SecurityUtils.getSubject().getPrincipal();
        String departIds = user.getDepartIds();
        Page<TeachingDepartDayLog> page = new Page<TeachingDepartDayLog>(pageNo, pageSize);
        boolean isAdmin = hasRole("admin") || hasRole("dev");
        List<TeachingDepartDayLog> list = teachingDepartDayLogService.list(new QueryWrapper<TeachingDepartDayLog>()
                        .select("depart_id, depart_name, sum(unit_open_count) unit_open_count," +
                                "sum(course_work_assign_count) course_work_assign_count," +
                                "sum(additional_work_assign_count) additional_work_assign_count," +
                                "sum(course_work_correct_count) course_work_correct_count," +
                                "sum(additional_work_correct_count) additional_work_correct_count," +
                                "sum(course_work_submit_count) course_work_submit_count,"+
                                "sum(additional_work_submit_count) additional_work_submit_count"
                        )
                        .in(!isAdmin, "depart_id", departIds.split(","))
                        .ge(StringUtils.isNotEmpty(startTime), "create_time", startTime)
                        .le(StringUtils.isNotEmpty(endTime), "create_time", endTime)
                       .groupBy("depart_id")

        );
        page.setRecords(list);
        return Result.ok(list);
    }

    /**
     * 按月聚合每日教学记录
     * @param startTime
     * @param endTime
     * @param pageNo
     * @param pageSize
     * @return
     */
    @ApiOperation(value="按月聚合每日教学记录", notes="按月聚合每日教学记录")
    @GetMapping("getReportGroupByMonth")
    public Result<?> getReportGroupByMonth(@RequestParam(required = false) String startTime,
                                            @RequestParam(required = false) String endTime,
                                            @RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
                                            @RequestParam(name="pageSize", defaultValue="10") Integer pageSize){
        //获取我负责的班级
        LoginUser user = (LoginUser) SecurityUtils.getSubject().getPrincipal();
        String departIds = user.getDepartIds();
        Page<TeachingDepartDayLog> page = new Page<TeachingDepartDayLog>(pageNo, pageSize);
        boolean isAdmin = hasRole("admin") || hasRole("dev");
        List<TeachingDepartDayLog> list = teachingDepartDayLogService.list(new QueryWrapper<TeachingDepartDayLog>()
                .select("create_time," +
                        "sum(unit_open_count) unit_open_count," +
                        "sum(course_work_assign_count) course_work_assign_count," +
                        "sum(additional_work_assign_count) additional_work_assign_count," +
                        "sum(course_work_correct_count) course_work_correct_count," +
                        "sum(additional_work_correct_count) additional_work_correct_count," +
                        "sum(course_work_submit_count) course_work_submit_count,"+
                        "sum(additional_work_submit_count) additional_work_submit_count"
                )
                .in(!isAdmin, "depart_id", departIds.split(","))
                .ge(StringUtils.isNotEmpty(startTime), "create_time", startTime)
                .le(StringUtils.isNotEmpty(endTime), "create_time", endTime)
                .groupBy("date_format(create_time, '%Y-%m')")

        );
        page.setRecords(list);
        return Result.ok(list);
    }
   
   /**
    * 分页列表查询
    *
    * @param teachingDepartDayLog
    * @param pageNo
    * @param pageSize
    * @param req
    * @return
    */
   @AutoLog(value = "班级每日教学记录-分页列表查询")
   @ApiOperation(value="班级每日教学记录-分页列表查询", notes="班级每日教学记录-分页列表查询")
   @GetMapping(value = "/list")
   public Result<?> queryPageList(TeachingDepartDayLog teachingDepartDayLog,
                                  @RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
                                  @RequestParam(name="pageSize", defaultValue="10") Integer pageSize,
                                  HttpServletRequest req) {
       QueryWrapper<TeachingDepartDayLog> queryWrapper = QueryGenerator.initQueryWrapper(teachingDepartDayLog, req.getParameterMap());
       Page<TeachingDepartDayLog> page = new Page<TeachingDepartDayLog>(pageNo, pageSize);
       IPage<TeachingDepartDayLog> pageList = teachingDepartDayLogService.page(page, queryWrapper);
       return Result.ok(pageList);
   }
   
   /**
    *   添加
    *
    * @param teachingDepartDayLog
    * @return
    */
   @AutoLog(value = "班级每日教学记录-添加")
   @ApiOperation(value="班级每日教学记录-添加", notes="班级每日教学记录-添加")
   @PostMapping(value = "/add")
   @ResponseStatus(HttpStatus.FORBIDDEN)
   public Result<?> add(@RequestBody TeachingDepartDayLog teachingDepartDayLog) {
       return manualWriteDisabled();
   }
   
   /**
    *  编辑
    *
    * @param teachingDepartDayLog
    * @return
    */
   @AutoLog(value = "班级每日教学记录-编辑")
   @ApiOperation(value="班级每日教学记录-编辑", notes="班级每日教学记录-编辑")
   @PutMapping(value = "/edit")
   @ResponseStatus(HttpStatus.FORBIDDEN)
   public Result<?> edit(@RequestBody TeachingDepartDayLog teachingDepartDayLog) {
       return manualWriteDisabled();
   }
   
   /**
    *   通过id删除
    *
    * @param id
    * @return
    */
   @AutoLog(value = "班级每日教学记录-通过id删除")
   @ApiOperation(value="班级每日教学记录-通过id删除", notes="班级每日教学记录-通过id删除")
   @DeleteMapping(value = "/delete")
   @ResponseStatus(HttpStatus.FORBIDDEN)
   public Result<?> delete(@RequestParam(name="id",required=true) String id) {
       return manualWriteDisabled();
   }
   
   /**
    *  批量删除
    *
    * @param ids
    * @return
    */
   @AutoLog(value = "班级每日教学记录-批量删除")
   @ApiOperation(value="班级每日教学记录-批量删除", notes="班级每日教学记录-批量删除")
   @DeleteMapping(value = "/deleteBatch")
   @ResponseStatus(HttpStatus.FORBIDDEN)
   public Result<?> deleteBatch(@RequestParam(name="ids",required=true) String ids) {
       return manualWriteDisabled();
   }
   
   /**
    * 通过id查询
    *
    * @param id
    * @return
    */
   @AutoLog(value = "班级每日教学记录-通过id查询")
   @ApiOperation(value="班级每日教学记录-通过id查询", notes="班级每日教学记录-通过id查询")
   @GetMapping(value = "/queryById")
   public Result<?> queryById(@RequestParam(name="id",required=true) String id) {
       TeachingDepartDayLog teachingDepartDayLog = teachingDepartDayLogService.getById(id);
       if(teachingDepartDayLog==null) {
           return Result.error("未找到对应数据");
       }
       return Result.ok(teachingDepartDayLog);
   }

   /**
   * 导出excel
   *
   * @param request
   * @param teachingDepartDayLog
   */
   @RequestMapping(value = "/exportXls")
   public ModelAndView exportXls(HttpServletRequest request, TeachingDepartDayLog teachingDepartDayLog) {
       return super.exportXls(request, teachingDepartDayLog, TeachingDepartDayLog.class, "班级每日教学记录");
   }

   /**
     * 通过excel导入数据
   *
   * @param request
   * @param response
   * @return
   */
   @RequestMapping(value = "/importExcel", method = RequestMethod.POST)
   @ResponseStatus(HttpStatus.FORBIDDEN)
   public Result<?> importExcel(HttpServletRequest request, HttpServletResponse response) {
       return manualWriteDisabled();
   }

   /**
    * These are derived event counters. Even administrators must not bypass the
    * shared department/day lock in addLog with generated CRUD or Excel import.
    * Keep the legacy routes so callers receive an explicit refusal.
    */
   private Result<?> manualWriteDisabled() {
       return Result.error(HttpStatus.FORBIDDEN.value(), "班级每日教学记录由教学事件自动生成，不支持人工修改");
   }

}
