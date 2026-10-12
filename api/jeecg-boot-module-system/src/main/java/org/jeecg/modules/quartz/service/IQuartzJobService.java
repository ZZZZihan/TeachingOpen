package org.jeecg.modules.quartz.service;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import java.util.Collection;
import java.util.List;
import org.jeecg.modules.quartz.entity.QuartzJob;

/** No generic save/update/import operations: every entry is an authorized command. */
public interface IQuartzJobService {
    IPage<QuartzJob> page(Page<QuartzJob> page, Wrapper<QuartzJob> query);
    List<QuartzJob> list(Wrapper<QuartzJob> query);
    QuartzJob getById(String id);
    boolean saveAndScheduleJob(QuartzJob job);
    boolean editAndScheduleJob(QuartzJob job);
    void deleteAndStopJobs(Collection<String> ids);
    void pauseJob(String jobClassName);
    boolean resumeJob(String jobClassName);
    void importJobs(List<QuartzJob> jobs);
}
