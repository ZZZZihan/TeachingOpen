package org.jeecg.modules.teaching.service;

import com.baomidou.mybatisplus.extension.service.IService;
import org.jeecg.modules.teaching.entity.TeachingDepartDayLog;
import org.jeecg.modules.teaching.enums.DepartDayLogType;
import org.jeecg.modules.teaching.enums.UnitViewLogResult;
import org.jeecg.modules.teaching.enums.WorkEventType;

/**
 * @Description: 班级每日教学记录
 * @Author: jeecg-boot
 * @Date:   2021-06-25
 * @Version: V1.0
 */
public interface ITeachingDepartDayLogService extends IService<TeachingDepartDayLog> {
    public void addLog(String departId, DepartDayLogType type);

    /** Record one additional-work assignment in the caller's transaction. */
    void recordAdditionalWorkAssignment(String departId);

    /** Atomically persist the lifetime unit event and its daily counter. */
    UnitViewLogResult recordUnitView(String userId, String unitId);

    /** Caller must hold the work row lock in its business transaction. */
    void recordWorkEvent(String workId, WorkEventType eventType);

}
