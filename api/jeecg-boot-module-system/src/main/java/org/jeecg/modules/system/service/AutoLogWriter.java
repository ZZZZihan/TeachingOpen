package org.jeecg.modules.system.service;

import org.jeecg.modules.system.entity.SysLog;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** Best-effort metadata audit, isolated from any surrounding business transaction.
 * No durable delivery, retry queue or business/audit atomicity is implied. */
@Service
public class AutoLogWriter {
    @Autowired
    private ISysLogService sysLogService;

    @Transactional(propagation = Propagation.REQUIRES_NEW, rollbackFor = Exception.class)
    public void save(SysLog entry) {
        if (!sysLogService.save(entry)) {
            throw new IllegalStateException("Audit insert did not persist a row");
        }
    }
}
