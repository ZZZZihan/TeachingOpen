package org.jeecg.modules.teaching.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import lombok.extern.slf4j.Slf4j;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.system.service.ISysFileService;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.jeecg.modules.teaching.mapper.TeachingWorkMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.util.StringUtils;

/** Reclaim work attachments only after a successful work deletion. */
@Service
@Slf4j
public class TeachingWorkAttachmentService {
    @Autowired
    private TeachingWorkMapper workMapper;
    @Autowired
    private ISysFileService fileService;
    @Autowired
    private PlatformTransactionManager transactionManager;

    public void cleanupAfterWorkDeletion(String fileId) {
        if (!StringUtils.hasText(fileId)) return;
        try {
            // afterCommit still has the old transaction's resources bound. A new
            // transaction is needed for the metadata removal to actually commit.
            TransactionTemplate cleanup = new TransactionTemplate(transactionManager);
            cleanup.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
            cleanup.execute(status -> {
                SysFile file = fileService.getById(fileId);
                if (file == null) return null;
                if (workMapper.selectCount(new QueryWrapper<TeachingWork>()
                        .eq("work_file", fileId).or().eq("work_cover", fileId)) > 0) return null;
                // Distinct file records can alias one physical object. Preserve
                // ambiguous aliases; work deletion is not a global file collector.
                if (fileService.count(new QueryWrapper<SysFile>().ne("id", fileId)
                        .eq("file_path", file.getFilePath())
                        .eq("file_location", file.getFileLocation())) > 0) return null;
                if (!fileService.deleteWithFile(fileId)) {
                    log.warn("Work attachment cleanup deferred; fileId={}", fileId);
                }
                return null;
            });
        } catch (RuntimeException error) {
            // The work deletion already committed. Do not report it as failed or
            // discard the metadata needed to diagnose/retry attachment cleanup.
            log.warn("Work attachment cleanup deferred; fileId={}", fileId, error);
        }
    }
}
