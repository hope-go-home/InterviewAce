package com.interviewace.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import com.interviewace.common.CurrentUser;
import com.interviewace.common.UserContext;
import com.interviewace.dto.ProfileStats;
import com.interviewace.service.ProfileService;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/** 个人能力画像：各域平均分/掌握度、薄弱域、连续学习天数、学习日历。 */
@Tag(name = "能力画像", description = "练习数据聚合统计")
@RestController
public class MeController {

    private final ProfileService profileService;

    public MeController(ProfileService profileService) {
        this.profileService = profileService;
    }

    @Operation(summary = "我的能力画像")
    @GetMapping("/me/profile")
    public ProfileStats profile(@CurrentUser UserContext user) {
        return profileService.profileStats(user.id());
    }
}
