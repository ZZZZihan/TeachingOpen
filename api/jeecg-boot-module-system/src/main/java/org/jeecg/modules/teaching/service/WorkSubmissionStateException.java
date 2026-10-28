package org.jeecg.modules.teaching.service;

import org.jeecg.common.exception.JeecgBootException;

/** A stale student editor must not overwrite a reviewed or unknown work state. */
public class WorkSubmissionStateException extends JeecgBootException {
    public WorkSubmissionStateException() {
        super("作业状态已变化，不能再保存或提交。请返回作业列表查看最新状态和反馈。");
    }
}
