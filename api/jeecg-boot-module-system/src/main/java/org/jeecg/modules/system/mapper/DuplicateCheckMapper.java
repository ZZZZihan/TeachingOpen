package org.jeecg.modules.system.mapper;

import org.apache.ibatis.annotations.Param;

/** All table/column choices are literal SQL owned by the mapper. */
public interface DuplicateCheckMapper {
    Long count(@Param("purpose") String purpose, @Param("fieldVal") String fieldVal, @Param("dataId") String dataId);
    String targetId(@Param("purpose") String purpose, @Param("dataId") String dataId);
}
