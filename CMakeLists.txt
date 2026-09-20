cmake_minimum_required(VERSION 3.15)
project(CrimeCraftLauncher
    VERSION 1.0.0
    DESCRIPTION "CrimeCraft GangWars Launcher"
    LANGUAGES C
)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")

if(MSVC)
    add_compile_options(/W4 /utf-8 /permissive- /Zc:__cplusplus)
    add_definitions(-D_CRT_SECURE_NO_WARNINGS -DUNICODE -D_UNICODE)
    set(PLATFORM_LIBS comctl32 shell32 advapi32)
elseif(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(-Wall -Wextra -Wpedantic -O2)
    add_definitions(-DUNICODE -D_UNICODE)
    set(PLATFORM_LIBS comctl32 shell32 advapi32)
    if(WIN32 AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
        if(EXISTS "${CMAKE_SOURCE_DIR}/comctl32v6.manifest")
            set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,--manifest,manifest:comctl32v6.manifest")
        endif()
    endif()
else()
    add_compile_options(-Wall -O2)
    add_definitions(-DUNICODE -D_UNICODE)
    set(PLATFORM_LIBS comctl32 shell32 advapi32)
endif()

add_executable(${PROJECT_NAME} src/launcher.c src/config.c)
target_link_libraries(${PROJECT_NAME} PRIVATE ${PLATFORM_LIBS})

if(WIN32)
    set_target_properties(${PROJECT_NAME} PROPERTIES
        WIN32_EXECUTABLE TRUE
        OUTPUT_NAME "CrimeCraftLauncher"
    )
    if(MSVC)
        target_link_options(${PROJECT_NAME} PRIVATE /SUBSYSTEM:WINDOWS)
    elseif(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_link_options(${PROJECT_NAME} PRIVATE -mwindows)
    endif()
endif()

install(TARGETS ${PROJECT_NAME} RUNTIME DESTINATION bin)

message(STATUS "===========================================")
message(STATUS "CrimeCraft Launcher - Configuracion")
message(STATUS "===========================================")
message(STATUS "  Compilador:   ${CMAKE_C_COMPILER_ID} ${CMAKE_C_COMPILER_VERSION}")
message(STATUS "  Sistema:      ${CMAKE_SYSTEM_NAME} ${CMAKE_SYSTEM_PROCESSOR}")
message(STATUS "  Build type:   ${CMAKE_BUILD_TYPE}")
message(STATUS "  Generator:    ${CMAKE_GENERATOR}")
message(STATUS "===========================================")
