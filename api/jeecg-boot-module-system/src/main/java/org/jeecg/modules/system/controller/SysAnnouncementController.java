package org.jeecg.modules.system.controller;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.system.query.QueryGenerator;
import org.jeecg.modules.system.entity.SysAnnouncement;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.model.AnnouncementCommand;
import org.jeecg.modules.system.service.*;
import org.jeecgframework.poi.excel.ExcelImportUtil;
import org.jeecgframework.poi.excel.def.NormalExcelConstants;
import org.jeecgframework.poi.excel.entity.ExportParams;
import org.jeecgframework.poi.excel.entity.ImportParams;
import org.jeecgframework.poi.excel.view.JeecgEntityExcelView;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;
import org.springframework.web.servlet.ModelAndView;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.InputStream;
import java.util.*;

@RestController
@RequestMapping("/sys/annountCement")
public class SysAnnouncementController {
    @Autowired private ISysAnnouncementService sysAnnouncementService;
    @Autowired private AnnouncementAccessService announcementAccess;
    @Autowired private AnnouncementCommandService announcementCommands;

    @GetMapping("/list")
    public Result<?> queryPageList(SysAnnouncement filter,
            @RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
            @RequestParam(name="pageSize", defaultValue="10") Integer pageSize, HttpServletRequest request) {
        announcementAccess.requireManager();
        filter.setDelFlag("0");
        QueryWrapper<SysAnnouncement> query = new QueryWrapper<>(filter);
        String column = request.getParameter("column");
        Map<String, String> sort = new HashMap<>();
        sort.put("createTime", "create_time"); sort.put("sendTime", "send_time");
        sort.put("startTime", "start_time"); sort.put("endTime", "end_time"); sort.put("titile", "titile");
        if (column != null && !column.isEmpty()) {
            if (!sort.containsKey(column)) throw new org.jeecg.common.exception.JeecgBootException("不支持的排序字段");
            query.orderBy(true, "asc".equals(request.getParameter("order")), sort.get(column));
        } else query.orderByDesc("create_time");
        IPage<SysAnnouncement> page = sysAnnouncementService.page(new Page<>(pageNo, pageSize), query);
        page.getRecords().forEach(AnnouncementAccessService::safe);
        return Result.ok(page);
    }

    @PostMapping("/add")
    public Result<?> add(@RequestBody AnnouncementCommand command) {
        announcementCommands.create(command);
        return Result.ok("添加成功！");
    }

    @PutMapping("/edit")
    public Result<?> eidt(@RequestBody AnnouncementCommand command) {
        announcementCommands.edit(command);
        return Result.ok("修改成功！");
    }

    @DeleteMapping("/delete")
    public Result<?> delete(@RequestParam(name="id") String id) {
        announcementCommands.delete(id);
        return Result.ok("删除成功！");
    }

    @DeleteMapping("/deleteBatch")
    public Result<?> deleteBatch(@RequestParam(name="ids") String ids) {
        announcementCommands.delete(ids);
        return Result.ok("删除成功！");
    }

    @GetMapping("/queryById")
    public Result<?> queryById(@RequestParam(name="id") String id) {
        return Result.ok(announcementAccess.requireRead(sysAnnouncementService.getById(id)));
    }

    @GetMapping("/doReleaseData")
    public Result<?> doReleaseData(@RequestParam(name="id") String id, HttpServletRequest request) {
        announcementCommands.publish(id, true);
        return Result.ok("该系统通知发布成功");
    }

    @GetMapping("/doReovkeData")
    public Result<?> doReovkeData(@RequestParam(name="id") String id, HttpServletRequest request) {
        announcementCommands.publish(id, false);
        return Result.ok("该系统通知撤销成功");
    }

    @GetMapping("/listByUser")
    public Result<?> listByUser() {
        SysUser user = announcementAccess.currentUser();
        announcementCommands.subscribeAvailable();
        Page<SysAnnouncement> notices = sysAnnouncementService.querySysCementPageByUserId(new Page<>(1, 5), user.getId(), "1");
        Page<SysAnnouncement> messages = sysAnnouncementService.querySysCementPageByUserId(new Page<>(1, 5), user.getId(), "2");
        Map<String,Object> data = new HashMap<>();
        data.put("anntMsgList", notices.getRecords()); data.put("anntMsgTotal", notices.getTotal());
        data.put("sysMsgList", messages.getRecords()); data.put("sysMsgTotal", messages.getTotal());
        return Result.ok(data);
    }

    @RequestMapping("/exportXls")
    public ModelAndView exportXls(SysAnnouncement filter, HttpServletRequest request) {
        SysUser user = announcementAccess.requireManager();
        filter.setDelFlag("0");
        QueryWrapper<SysAnnouncement> query = QueryGenerator.initQueryWrapper(filter, request.getParameterMap());
        List<SysAnnouncement> rows = sysAnnouncementService.list(query);
        rows.forEach(AnnouncementAccessService::safe);
        ModelAndView view = new ModelAndView(new JeecgEntityExcelView());
        view.addObject(NormalExcelConstants.FILE_NAME, "系统通告列表");
        view.addObject(NormalExcelConstants.CLASS, SysAnnouncement.class);
        view.addObject(NormalExcelConstants.PARAMS, new ExportParams("系统通告列表数据", "导出人:" + user.getRealname(), "导出信息"));
        view.addObject(NormalExcelConstants.DATA_LIST, rows);
        return view;
    }

    @PostMapping("/importExcel")
    public Result<?> importExcel(HttpServletRequest request, HttpServletResponse response) throws Exception {
        // Check before reading the upload; authorization errors must not become generic import failures.
        announcementAccess.requireManager();
        if (!(request instanceof MultipartHttpServletRequest)) return Result.error("请上传通知文件");
        List<AnnouncementCommand> commands = new ArrayList<>();
        for (MultipartFile file : ((MultipartHttpServletRequest) request).getFileMap().values()) {
            ImportParams params = new ImportParams(); params.setTitleRows(2); params.setHeadRows(1);
            try (InputStream input = file.getInputStream()) {
                List<SysAnnouncement> rows = ExcelImportUtil.importExcel(input, SysAnnouncement.class, params);
                for (SysAnnouncement row : rows) commands.add(AnnouncementCommand.from(row));
            }
        }
        announcementCommands.importAnnouncements(commands);
        return Result.ok("文件导入成功！数据行数：" + commands.size());
    }

    /** A read receipt refreshes only the current user's tabs. Publishing owns broadcasts. */
    @GetMapping("/syncNotic")
    public Result<?> syncNotic(@RequestParam(name="anntId", required=false) String id, HttpServletRequest request) {
        announcementCommands.syncCurrentUser(id);
        return Result.ok("通知状态已同步");
    }
}
