using System.Text.Json;
using ValveResourceFormat.NavMesh;

if (args.Length != 2 || File.Exists(args[1]))
{
    Console.Error.WriteLine("Usage: NavExport INPUT.nav NEW_OUTPUT.json");
    return 1;
}
try
{
    var nav = new NavMeshFile();
    nav.Read(args[0]);
    var data = new
    {
        schema_version = 1,
        source = Path.GetFullPath(args[0]),
        parser = "ValveResourceFormat 20.0.6980",
        version = nav.Version,
        subversion = nav.SubVersion,
        analyzed = nav.IsAnalyzed,
        ladder_count = nav.Ladders.Length,
        areas = nav.Areas.Values.Select(a => new
        {
            id = a.AreaId,
            hull = a.HullIndex,
            flags = (long)a.AttributeFlags,
            movable_mesh_id = a.MovableMeshId,
            corners = a.Corners.Select(p => new[] { p.X, p.Y, p.Z }).ToArray(),
            connections = a.Connections.SelectMany((edge, index) => edge.Select(c => new { target = c.AreaId, source_edge = index, target_edge = c.EdgeId })).ToArray(),
            ladders_above = a.LaddersAbove,
            ladders_below = a.LaddersBelow
        }).ToArray()
    };
    Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[1]))!);
    using var file = new FileStream(args[1], FileMode.CreateNew);
    JsonSerializer.Serialize(file, data, new JsonSerializerOptions { WriteIndented = true });
    Console.WriteLine($"Exported {nav.Areas.Count} navigation areas, {nav.Ladders.Length} ladders.");
    return 0;
}
catch (Exception e)
{
    Console.Error.WriteLine(e.ToString());
    return 1;
}
