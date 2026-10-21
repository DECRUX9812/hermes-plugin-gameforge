// Pixel-art import settings for everything GameForge drops under Assets/Resources/GameForge:
// point filtering, no resize to power-of-two (atlas rects must stay exact), no compression.
using UnityEditor;
using UnityEngine;

namespace GameForge.EditorTools
{
    public class GameForgeImport : AssetPostprocessor
    {
        void OnPreprocessTexture()
        {
            if (!assetPath.Contains("/GameForge/")) return;
            var ti = (TextureImporter)assetImporter;
            ti.textureType = TextureImporterType.Default;
            ti.npotScale = TextureImporterNPOTScale.None;
            ti.filterMode = FilterMode.Point;
            ti.mipmapEnabled = false;
            ti.textureCompression = TextureImporterCompression.Uncompressed;
            ti.alphaIsTransparency = true;
            ti.wrapMode = TextureWrapMode.Clamp;
        }
    }
}
