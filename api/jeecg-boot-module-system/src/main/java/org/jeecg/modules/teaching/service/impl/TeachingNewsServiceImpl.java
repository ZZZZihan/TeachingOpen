package org.jeecg.modules.teaching.service.impl;

import org.jeecg.modules.teaching.entity.TeachingNews;
import org.jeecg.modules.teaching.mapper.TeachingNewsMapper;
import org.jeecg.modules.teaching.service.ITeachingNewsService;
import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import java.util.Collection;
import org.jeecg.modules.teaching.util.RichTextSanitizer;

/**
 * @Description: 资讯
 * @Author: jeecg-boot
 * @Date:   2024-06-19
 * @Version: V1.0
 */
@Service
public class TeachingNewsServiceImpl extends ServiceImpl<TeachingNewsMapper, TeachingNews> implements ITeachingNewsService {
    private void sanitize(TeachingNews news) {
        news.setNewsContent(RichTextSanitizer.sanitize(news.getNewsContent()));
    }

    @Override
    public boolean save(TeachingNews news) {
        sanitize(news);
        return super.save(news);
    }

    @Override
    public boolean updateById(TeachingNews news) {
        sanitize(news);
        return super.updateById(news);
    }

    @Override
    public boolean saveBatch(Collection<TeachingNews> news, int batchSize) {
        news.forEach(this::sanitize);
        return super.saveBatch(news, batchSize);
    }
}
