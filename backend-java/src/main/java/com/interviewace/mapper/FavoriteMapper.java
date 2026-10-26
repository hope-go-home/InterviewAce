package com.interviewace.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.interviewace.entity.Favorite;

@Mapper
public interface FavoriteMapper extends BaseMapper<Favorite> {
}
