package org.jeecg.modules.teaching.service;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import org.jeecg.modules.teaching.entity.TeachingMenu;
import org.jeecg.modules.teaching.model.TreeModel;
import java.util.Collection;
import java.util.List;

/** Explicit commands prevent inherited generic writes from bypassing validation/authorization. */
public interface ITeachingMenuService {
    List<TeachingMenu> listPublic();
    List<TeachingMenu> listManaged(Wrapper<TeachingMenu> query);
    List<TreeModel> queryListByParentId(String parentId);
    void addPermission(TeachingMenu menu);
    void editPermission(TeachingMenu menu);
    void deletePermission(String id);
    void deletePermissions(Collection<String> ids);
}
