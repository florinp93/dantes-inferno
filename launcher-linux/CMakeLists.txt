set(CMAKE_AUTOMOC ON)

add_executable(dantes_inferno_launcher
    main.cpp
    main_window.cpp
    main_window.h
    game_config.cpp
    game_config.h
    import_service.cpp
    import_service.h
)

target_link_libraries(dantes_inferno_launcher PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
)

target_compile_features(dantes_inferno_launcher PRIVATE cxx_std_23)
target_compile_definitions(dantes_inferno_launcher PRIVATE
    DANTES_LAUNCHER_VERSION="0.1.0"
)

if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
    target_compile_options(dantes_inferno_launcher PRIVATE -march=armv8.4-a)
endif()

include(GNUInstallDirs)
install(TARGETS dantes_inferno_launcher
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})

if(DANTESINFERNO_LAUNCHER_BUILD_TESTS)
    find_package(Qt6 6.4 COMPONENTS Test QUIET)
    if(TARGET Qt6::Test)
        add_executable(launcher_config_test
            tests/config_test.cpp
            game_config.cpp
            game_config.h
            import_service.cpp
            import_service.h
        )
        target_include_directories(launcher_config_test PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
        target_link_libraries(launcher_config_test PRIVATE Qt6::Core Qt6::Test)
        add_test(NAME launcher_config_test COMMAND launcher_config_test)
    endif()
endif()
