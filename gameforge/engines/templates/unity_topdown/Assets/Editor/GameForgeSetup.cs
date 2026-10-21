// Batch-mode entry points:
//   Unity -batchmode -quit -projectPath <unity> -executeMethod GameForge.EditorTools.Setup.CreateScene -logFile -
//   Unity -batchmode -quit -projectPath <unity> -executeMethod GameForge.EditorTools.Builds.WebGL -logFile -
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace GameForge.EditorTools
{
    public static class Setup
    {
        public const string ScenePath = "Assets/Scenes/Main.unity";

        [MenuItem("GameForge/Create Main Scene")]
        public static void CreateScene()
        {
            AssetDatabase.Refresh();
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var camGo = new GameObject("Main Camera");
            camGo.tag = "MainCamera";
            var cam = camGo.AddComponent<Camera>();
            cam.orthographic = true;
            cam.clearFlags = CameraClearFlags.SolidColor;
            camGo.transform.position = new Vector3(0, 0, -10);
            camGo.AddComponent<AudioListener>();
            new GameObject("GameForge").AddComponent<GameForge.GameForgeTopDown>();
            Directory.CreateDirectory("Assets/Scenes");
            EditorSceneManager.SaveScene(scene, ScenePath);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            Debug.Log("GAMEFORGE_SETUP_DONE");
        }
    }

    public static class Builds
    {
        static void Run(BuildTarget target, string path)
        {
            if (!File.Exists(Setup.ScenePath)) Setup.CreateScene();
            var opts = new BuildPlayerOptions
            {
                scenes = new[] { Setup.ScenePath }, locationPathName = path, target = target, options = BuildOptions.None,
            };
            var report = BuildPipeline.BuildPlayer(opts);
            Debug.Log("GAMEFORGE_BUILD " + report.summary.result + " " + path);
            if (report.summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded) EditorApplication.Exit(1);
        }

        public static void WebGL() => Run(BuildTarget.WebGL, "../dist/unity-webgl");
        public static void Android() => Run(BuildTarget.Android, "../dist/unity-android/game.apk");
        public static void Windows() => Run(BuildTarget.StandaloneWindows64, "../dist/unity-windows/Game.exe");
        public static void Linux() => Run(BuildTarget.StandaloneLinux64, "../dist/unity-linux/game.x86_64");
        public static void MacOS() => Run(BuildTarget.StandaloneOSX, "../dist/unity-macos/Game.app");
    }
}
