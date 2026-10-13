package org.jeecg.modules.quartz.service.impl;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import java.util.*;
import org.jeecg.common.constant.CommonConstant;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.modules.quartz.entity.QuartzJob;
import org.jeecg.modules.quartz.mapper.QuartzJobMapper;
import org.jeecg.modules.quartz.service.IQuartzJobService;
import org.jeecg.modules.quartz.service.ManagedJobTypes;
import org.jeecg.modules.system.service.AccountAdministrationService;
import org.jeecg.modules.system.service.InfrastructureAccessService;
import org.quartz.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class QuartzJobServiceImpl implements IQuartzJobService {
    private final InfrastructureAccessService access;
    private final QuartzJobMapper jobs;
    private final Scheduler scheduler;

    public QuartzJobServiceImpl(InfrastructureAccessService access, QuartzJobMapper jobs, Scheduler scheduler) {
        this.access = access; this.jobs = jobs; this.scheduler = scheduler;
    }

    @Override public IPage<QuartzJob> page(Page<QuartzJob> page, Wrapper<QuartzJob> query) {
        access.requireOperator();
        IPage<QuartzJob> result = jobs.selectPage(page, query);
        result.getRecords().forEach(this::describeType);
        return result;
    }
    @Override public List<QuartzJob> list(Wrapper<QuartzJob> query) {
        access.requireOperator();
        List<QuartzJob> values = jobs.selectList(query); values.forEach(this::describeType); return values;
    }
    @Override public QuartzJob getById(String id) {
        access.requireOperator(); return describeType(jobs.selectById(id));
    }

    @Override @Transactional(rollbackFor = Exception.class)
    public boolean saveAndScheduleJob(QuartzJob command) {
        access.requireOperator();
        QuartzJob value = fields(command, null);
        requireUnique(value);
        if (jobs.insert(value) != 1) throw new JeecgBootException("任务保存失败");
        if (CommonConstant.STATUS_NORMAL.equals(value.getStatus())) schedule(value);
        return true;
    }

    @Override @Transactional(rollbackFor = Exception.class)
    public boolean editAndScheduleJob(QuartzJob command) {
        access.requireOperator();
        if (command == null || command.getId() == null) throw new JeecgBootException("任务不存在");
        QuartzJob current = required(command.getId());
        QuartzJob value = fields(command, current);
        if (jobs.updateById(value) != 1) throw new JeecgBootException("任务更新失败");
        deleteSchedule(current.getJobClassName());
        if (CommonConstant.STATUS_NORMAL.equals(value.getStatus())) schedule(value);
        return true;
    }

    @Override @Transactional(rollbackFor = Exception.class)
    public void deleteAndStopJobs(Collection<String> requested) {
        access.requireOperator();
        List<String> ids = AccountAdministrationService.ids(requested);
        List<QuartzJob> values = new ArrayList<>();
        for (String id : ids) values.add(required(id));
        if (jobs.deleteBatchIds(ids) != ids.size()) throw new JeecgBootException("任务删除失败");
        for (QuartzJob value : values) deleteSchedule(value.getJobClassName());
    }

    @Override @Transactional(rollbackFor = Exception.class)
    public void pauseJob(String jobClassName) {
        access.requireOperator();
        QuartzJob current = requiredByClass(jobClassName);
        QuartzJob patch = new QuartzJob(); patch.setId(current.getId()); patch.setStatus(CommonConstant.STATUS_DISABLE);
        if (jobs.updateById(patch) != 1) throw new JeecgBootException("任务更新失败");
        try { scheduler.pauseJob(JobKey.jobKey(current.getJobClassName())); }
        catch (SchedulerException e) { throw new JeecgBootException("暂停任务失败", e); }
    }

    @Override @Transactional(rollbackFor = Exception.class)
    public boolean resumeJob(String jobClassName) {
        access.requireOperator();
        QuartzJob current = requiredByClass(jobClassName);
        validate(current);
        QuartzJob patch = new QuartzJob(); patch.setId(current.getId()); patch.setStatus(CommonConstant.STATUS_NORMAL);
        if (jobs.updateById(patch) != 1) throw new JeecgBootException("任务更新失败");
        deleteSchedule(current.getJobClassName()); schedule(current);
        return true;
    }

    @Override @Transactional(rollbackFor = Exception.class)
    public void importJobs(List<QuartzJob> commands) {
        access.requireOperator();
        if (commands == null || commands.isEmpty() || commands.size() > 100) throw new JeecgBootException("每次导入1至100个任务");
        Set<String> types = new HashSet<>(); List<QuartzJob> values = new ArrayList<>();
        for (QuartzJob command : commands) {
            QuartzJob value = fields(command, null);
            if (!types.add(value.getJobClassName())) throw new JeecgBootException("任务类型重复");
            requireUnique(value); values.add(value);
        }
        // Validate every row before changing either the database or scheduler.
        for (QuartzJob value : values) {
            if (jobs.insert(value) != 1) throw new JeecgBootException("任务导入失败");
        }
        for (QuartzJob value : values) if (CommonConstant.STATUS_NORMAL.equals(value.getStatus())) schedule(value);
    }

    private QuartzJob required(String id) {
        QuartzJob value = jobs.selectById(id);
        if (value == null || !id.equals(value.getId())) throw new JeecgBootException("任务不存在");
        return value;
    }
    private QuartzJob requiredByClass(String name) {
        ManagedJobTypes.typeForClass(name);
        QuartzJob value = jobs.selectOne(new QueryWrapper<QuartzJob>().eq("job_class_name", name));
        if (value == null || !name.equals(value.getJobClassName())) throw new JeecgBootException("任务不存在");
        return value;
    }
    private void requireUnique(QuartzJob value) {
        List<QuartzJob> existing = jobs.findByJobClassName(value.getJobClassName());
        if (existing != null && !existing.isEmpty()) throw new JeecgBootException("该任务类型已存在");
    }
    private QuartzJob fields(QuartzJob command, QuartzJob current) {
        if (command == null) throw new JeecgBootException("任务不能为空");
        String type = command.getJobType();
        if (type == null && current != null) type = ManagedJobTypes.typeForClass(current.getJobClassName());
        String className = ManagedJobTypes.jobClass(type).getName();
        if ((command.getJobClassName() != null && !className.equals(command.getJobClassName()))
                || (current != null && !current.getJobClassName().equals(className))) {
            throw new JeecgBootException("任务类型不可更改");
        }
        QuartzJob value = new QuartzJob();
        if (current != null) value.setId(current.getId());
        value.setJobType(type); value.setJobClassName(className); value.setCronExpression(command.getCronExpression());
        value.setDescription(command.getDescription()); value.setParameter(command.getParameter());
        value.setStatus(command.getStatus()); value.setDelFlag(CommonConstant.DEL_FLAG_0);
        validate(value); return value;
    }
    private void validate(QuartzJob value) {
        ManagedJobTypes.typeForClass(value.getJobClassName());
        if (value.getCronExpression() == null || !CronExpression.isValidExpression(value.getCronExpression())
                || (!CommonConstant.STATUS_NORMAL.equals(value.getStatus()) && !CommonConstant.STATUS_DISABLE.equals(value.getStatus()))) {
            throw new JeecgBootException("任务计划或状态不正确");
        }
    }
    private QuartzJob describeType(QuartzJob value) {
        if (value == null) return null;
        // Legacy unknown rows remain inspectable/deletable, but cannot be resumed or edited into execution.
        try { value.setJobType(ManagedJobTypes.typeForClass(value.getJobClassName())); }
        catch (JeecgBootException unsupported) { value.setJobType(null); }
        return value;
    }
    private void schedule(QuartzJob value) {
        Class<? extends Job> type = ManagedJobTypes.jobClass(ManagedJobTypes.typeForClass(value.getJobClassName()));
        JobDetail detail = JobBuilder.newJob(type).withIdentity(value.getJobClassName())
                .usingJobData("parameter", value.getParameter()).build();
        CronTrigger trigger = TriggerBuilder.newTrigger().withIdentity(value.getJobClassName())
                .withSchedule(CronScheduleBuilder.cronSchedule(value.getCronExpression())).build();
        try { scheduler.scheduleJob(detail, trigger); }
        catch (SchedulerException e) { throw new JeecgBootException("创建任务失败", e); }
    }
    private void deleteSchedule(String name) {
        try { scheduler.deleteJob(JobKey.jobKey(name)); }
        catch (SchedulerException e) { throw new JeecgBootException("删除任务失败", e); }
    }
}
