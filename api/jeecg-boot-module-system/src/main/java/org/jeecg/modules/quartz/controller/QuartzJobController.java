package org.jeecg.modules.quartz.controller;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import java.io.InputStream;
import java.util.*;
import javax.servlet.http.HttpServletRequest;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.query.QueryGenerator;
import org.jeecg.modules.quartz.entity.QuartzJob;
import org.jeecg.modules.quartz.service.IQuartzJobService;
import org.jeecg.modules.quartz.service.ManagedJobTypes;
import org.jeecg.modules.system.service.AccountAdministrationService;
import org.jeecg.modules.system.service.InfrastructureAccessService;
import org.jeecgframework.poi.excel.ExcelImportUtil;
import org.jeecgframework.poi.excel.def.NormalExcelConstants;
import org.jeecgframework.poi.excel.entity.ExportParams;
import org.jeecgframework.poi.excel.entity.ImportParams;
import org.jeecgframework.poi.excel.view.JeecgEntityExcelView;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;
import org.springframework.web.servlet.ModelAndView;

@RestController
@RequestMapping("/sys/quartzJob")
public class QuartzJobController {
    private final InfrastructureAccessService access;
    private final IQuartzJobService jobs;

    public QuartzJobController(InfrastructureAccessService access, IQuartzJobService jobs) {
        this.access = access; this.jobs = jobs;
    }

    @GetMapping("/list")
    public Result<?> queryPageList(QuartzJob job, @RequestParam(defaultValue = "1") Integer pageNo,
            @RequestParam(defaultValue = "10") Integer pageSize, HttpServletRequest request) {
        access.requireOperator();
        return Result.ok(jobs.page(new Page<>(pageNo, pageSize), query(job, request)));
    }

    @GetMapping("/types")
    public Result<?> types() { access.requireOperator(); return Result.ok(ManagedJobTypes.names()); }

    @PostMapping("/add")
    public Result<?> add(@RequestBody QuartzJob job) {
        access.requireOperator(); jobs.saveAndScheduleJob(job); return Result.ok("创建定时任务成功");
    }

    @PutMapping("/edit")
    public Result<?> edit(@RequestBody QuartzJob job) {
        access.requireOperator(); jobs.editAndScheduleJob(job); return Result.ok("更新定时任务成功");
    }

    @DeleteMapping("/delete")
    public Result<?> delete(@RequestParam String id) {
        access.requireOperator(); jobs.deleteAndStopJobs(Collections.singletonList(id)); return Result.ok("删除成功");
    }

    @DeleteMapping("/deleteBatch")
    public Result<?> deleteBatch(@RequestParam String ids) {
        access.requireOperator(); jobs.deleteAndStopJobs(AccountAdministrationService.ids(ids)); return Result.ok("批量删除成功");
    }

    @GetMapping("/pause")
    public Result<?> pauseJob(@RequestParam String jobClassName) {
        access.requireOperator(); jobs.pauseJob(jobClassName); return Result.ok("暂停定时任务成功");
    }

    @GetMapping("/resume")
    public Result<?> resumeJob(@RequestParam String jobClassName) {
        access.requireOperator(); jobs.resumeJob(jobClassName); return Result.ok("恢复定时任务成功");
    }

    @GetMapping("/queryById")
    public Result<?> queryById(@RequestParam String id) {
        access.requireOperator(); return Result.ok(jobs.getById(id));
    }

    @RequestMapping("/exportXls")
    public ModelAndView exportXls(HttpServletRequest request, QuartzJob job) {
        access.requireOperator();
        ModelAndView view = new ModelAndView(new JeecgEntityExcelView());
        view.addObject(NormalExcelConstants.FILE_NAME, "定时任务列表");
        view.addObject(NormalExcelConstants.CLASS, QuartzJob.class);
        view.addObject(NormalExcelConstants.PARAMS, new ExportParams("定时任务列表", "", "任务"));
        view.addObject(NormalExcelConstants.DATA_LIST, jobs.list(query(job, request)));
        return view;
    }

    @PostMapping("/importExcel")
    public Result<?> importExcel(HttpServletRequest request) throws Exception {
        access.requireOperator();
        if (!(request instanceof MultipartHttpServletRequest)) throw new JeecgBootException("请选择导入文件");
        ImportParams params = new ImportParams(); params.setTitleRows(2); params.setHeadRows(1);
        List<QuartzJob> values = new ArrayList<>();
        for (MultipartFile file : ((MultipartHttpServletRequest) request).getFileMap().values()) {
            try (InputStream input = file.getInputStream()) {
                values.addAll(ExcelImportUtil.importExcel(input, QuartzJob.class, params));
            }
        }
        jobs.importJobs(values);
        return Result.ok("导入成功，共" + values.size() + "条");
    }

    private QueryWrapper<QuartzJob> query(QuartzJob job, HttpServletRequest request) {
        return QueryGenerator.initQueryWrapper(job, request.getParameterMap());
    }

    @ExceptionHandler(UnauthorizedException.class)
    @ResponseStatus(HttpStatus.FORBIDDEN)
    public Result<?> denied(UnauthorizedException ignored) { return Result.error(403, "没有运维管理权限"); }
}
