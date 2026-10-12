package org.jeecg.modules.system.controller;

import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.api.vo.Result;
import org.jeecg.modules.system.entity.SysAnnouncementSend;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.model.AnnouncementSendModel;
import org.jeecg.modules.system.service.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import javax.servlet.http.HttpServletRequest;

@RestController
@RequestMapping("/sys/sysAnnouncementSend")
public class SysAnnouncementSendController {
    @Autowired private ISysAnnouncementSendService sysAnnouncementSendService;
    @Autowired private ISysAnnouncementService sysAnnouncementService;
    @Autowired private AnnouncementAccessService announcementAccess;
    @Autowired private AnnouncementCommandService announcementCommands;

    @GetMapping("/list")
    public Result<?> queryPageList(SysAnnouncementSend filter,
            @RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
            @RequestParam(name="pageSize", defaultValue="10") Integer pageSize, HttpServletRequest request) {
        announcementAccess.requireManager();
        return Result.ok(sysAnnouncementSendService.page(new Page<>(pageNo, pageSize),
                new QueryWrapper<>(filter).orderByDesc("create_time")));
    }

    // Receipt identities/audiences are exclusively managed with their parent notification.
    @PostMapping("/add")
    public Result<?> add(@RequestBody SysAnnouncementSend ignored) { throw receiptWriteDenied(); }
    @PutMapping("/edit")
    public Result<?> eidt(@RequestBody SysAnnouncementSend ignored) { throw receiptWriteDenied(); }
    @DeleteMapping("/delete")
    public Result<?> delete(@RequestParam(name="id") String ignored) { throw receiptWriteDenied(); }
    @DeleteMapping("/deleteBatch")
    public Result<?> deleteBatch(@RequestParam(name="ids") String ignored) { throw receiptWriteDenied(); }
    private UnauthorizedException receiptWriteDenied() { return new UnauthorizedException("请通过通知管理维护收件人"); }

    @GetMapping("/queryById")
    public Result<?> queryById(@RequestParam(name="id") String id) {
        SysUser user = announcementAccess.currentUser();
        SysAnnouncementSend receipt = sysAnnouncementSendService.getById(id);
        if (receipt == null || (!user.getId().equals(receipt.getUserId()) && !announcementAccess.isManager(user)))
            throw new UnauthorizedException("没有此通知的读取权限");
        announcementAccess.requireRead(sysAnnouncementService.getById(receipt.getAnntId()));
        return Result.ok(receipt);
    }

    @PutMapping("/editByAnntIdAndUserId")
    public Result<?> editById(@RequestBody JSONObject json) {
        announcementCommands.markRead(json.getString("anntId"));
        return Result.ok("已读");
    }

    @GetMapping("/getMyAnnouncementSend")
    public Result<?> getMyAnnouncementSend(AnnouncementSendModel filter,
            @RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
            @RequestParam(name="pageSize", defaultValue="10") Integer pageSize) {
        filter.setUserId(announcementAccess.currentUser().getId());
        announcementCommands.subscribeAvailable();
        return Result.ok(sysAnnouncementSendService.getMyAnnouncementSendPage(new Page<>(pageNo, pageSize), filter));
    }

    @PutMapping("/readAll")
    public Result<?> readAll() {
        announcementCommands.markAllRead();
        return Result.ok("全部已读");
    }
}
